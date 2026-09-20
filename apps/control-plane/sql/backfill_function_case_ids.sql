-- 回填历史功能用例候选结果里的 case_id
--
-- 背景：功能用例的编号由平台分配。新产物在生成/导入时已带上，但历史候选结果
-- （ai_generate_stage_attempts.output_content）里有些用例没有 case_id，导致审核页
-- 看不到编号，导入时也只能现发一个新编号。本脚本给这些缺失的用例补上 UUID。
--
-- 影响范围：stage 为 detailed_cases 且 cases 非空的候选结果，逐条检查用例元素，
-- 只为「缺少 case_id」「case_id 为 null」「case_id 为空串」的用例生成 UUID，
-- 已有序号的用例原样保留。脚本可重复执行，重复执行不会改动已补过的数据。
--
-- 注意：写回时内容会经过 MySQL 的 JSON 规范化（键顺序、缩进与转义形式可能与原始
-- 文本不同），业务字段与取值不变；平台读的是解析后的结构，不受影响。
--
-- 用法：
--   mysql --default-character-set=utf8mb4 -h <host> -u <user> -p <database> < backfill_function_case_ids.sql   # 干跑，只统计
--   CALL backfill_function_case_ids(0);                                                                      # 实际写入
--
-- 回滚：
--   UPDATE ai_generate_stage_attempts AS a
--     JOIN ai_generate_stage_attempts_caseid_backup AS b ON b.id = a.id
--      SET a.output_content = b.output_content;
--   DROP TABLE ai_generate_stage_attempts_caseid_backup;

CREATE TABLE IF NOT EXISTS ai_generate_stage_attempts_caseid_backup (
  id VARCHAR(64) NOT NULL PRIMARY KEY,
  output_content LONGTEXT,
  backed_up_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;

INSERT IGNORE INTO ai_generate_stage_attempts_caseid_backup (id, output_content)
SELECT a.id, a.output_content
  FROM ai_generate_stage_attempts AS a
  JOIN ai_generate_run_stages AS s ON s.id = a.stage_id
 WHERE s.stage = 'detailed_cases'
   AND JSON_VALID(a.output_content)
   AND JSON_LENGTH(JSON_EXTRACT(a.output_content, '$.cases')) > 0;

DROP PROCEDURE IF EXISTS backfill_function_case_ids;

DELIMITER //
CREATE PROCEDURE backfill_function_case_ids(IN p_dry_run TINYINT)
BEGIN
  DECLARE done INT DEFAULT 0;
  DECLARE v_id VARCHAR(64);
  DECLARE v_content LONGTEXT;
  DECLARE v_cases JSON;
  DECLARE v_element JSON;
  DECLARE v_current JSON;
  DECLARE v_new_cases JSON;
  DECLARE v_index INT DEFAULT 0;
  DECLARE v_length INT DEFAULT 0;
  DECLARE v_needs_id INT DEFAULT 0;
  DECLARE v_added INT DEFAULT 0;
  DECLARE v_attempts INT DEFAULT 0;
  DECLARE v_cases_seen INT DEFAULT 0;
  DECLARE v_identifiers INT DEFAULT 0;

  DECLARE attempts CURSOR FOR
    SELECT a.id, a.output_content
      FROM ai_generate_stage_attempts AS a
      JOIN ai_generate_run_stages AS s ON s.id = a.stage_id
     WHERE s.stage = 'detailed_cases'
       AND JSON_VALID(a.output_content)
       AND JSON_LENGTH(JSON_EXTRACT(a.output_content, '$.cases')) > 0
     ORDER BY a.id;

  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;

  OPEN attempts;
  read_attempts: LOOP
    FETCH attempts INTO v_id, v_content;
    IF done = 1 THEN
      LEAVE read_attempts;
    END IF;

    SET v_cases = JSON_EXTRACT(v_content, '$.cases');
    SET v_length = JSON_LENGTH(v_cases);
    SET v_index = 0;
    SET v_added = 0;
    SET v_new_cases = JSON_ARRAY();

    WHILE v_index < v_length DO
      SET v_element = JSON_EXTRACT(v_cases, CONCAT('$[', v_index, ']'));
      SET v_needs_id = 0;

      IF JSON_TYPE(v_element) = 'OBJECT' THEN
        SET v_current = JSON_EXTRACT(v_element, '$.case_id');
        IF v_current IS NULL THEN
          SET v_needs_id = 1;
        ELSEIF JSON_TYPE(v_current) = 'NULL' THEN
          SET v_needs_id = 1;
        ELSEIF JSON_TYPE(v_current) = 'STRING' AND JSON_UNQUOTE(v_current) = '' THEN
          SET v_needs_id = 1;
        END IF;
        IF v_needs_id = 1 THEN
          SET v_element = JSON_SET(v_element, '$.case_id', UUID());
          SET v_added = v_added + 1;
        END IF;
      END IF;

      SET v_new_cases = JSON_ARRAY_APPEND(v_new_cases, '$', v_element);
      SET v_index = v_index + 1;
    END WHILE;

    IF v_added > 0 THEN
      SET v_attempts = v_attempts + 1;
      SET v_cases_seen = v_cases_seen + v_length;
      SET v_identifiers = v_identifiers + v_added;
      IF p_dry_run = 0 THEN
        UPDATE ai_generate_stage_attempts
           SET output_content = CAST(JSON_SET(CAST(v_content AS JSON), '$.cases', v_new_cases) AS CHAR)
         WHERE id = v_id;
      END IF;
      SELECT CONCAT(IF(p_dry_run = 1, '[dry-run] ', ''), v_id,
                    ' 共 ', v_length, ' 条用例，补 ', v_added, ' 个编号') AS detail;
    END IF;
  END LOOP;
  CLOSE attempts;

  SELECT IF(p_dry_run = 1, 'dry-run', 'applied') AS mode,
         v_attempts AS attempts_touched,
         v_cases_seen AS cases_scanned,
         v_identifiers AS identifiers_added;
END //
DELIMITER ;

-- 默认干跑：确认明细与统计无误后，再执行 CALL backfill_function_case_ids(0);
CALL backfill_function_case_ids(1);
