import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import exec from 'k6/execution';
import { Counter } from 'k6/metrics';

const plan = JSON.parse(open('plan.json'));

export const options = plan.options;

const datasets = {};
for (const meta of plan.data) {
  datasets[meta.name] = new SharedArray(meta.name, function () {
    return JSON.parse(open('data/' + meta.name + '.json'));
  });
}

const bizFailures = new Counter('biz_failures');

function asString(value) {
  if (value === undefined || value === null) {
    return '';
  }
  return String(value);
}

function uuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function resolveString(text, ctx) {
  return text.replace(/\{\{\s*([^{}]+?)\s*\}\}/g, function (_match, expression) {
    const key = expression.trim();
    if (key === 'uuid') {
      return uuid();
    }
    if (key === 'timestamp') {
      return String(Date.now());
    }
    if (key === 'iteration') {
      return String(exec.scenario.iterationInTest);
    }
    if (key === 'vu') {
      return String(exec.vu.idInTest);
    }
    if (key.indexOf('data.') === 0) {
      return asString(ctx.data[key.slice(5)]);
    }
    if (key.indexOf('var.') === 0) {
      return asString(ctx.vars[key.slice(4)]);
    }
    if (key.indexOf('env.') === 0) {
      return asString(ctx.env[key.slice(4)]);
    }
    return '';
  });
}

function resolveValue(value, ctx) {
  if (typeof value === 'string') {
    return resolveString(value, ctx);
  }
  if (Array.isArray(value)) {
    return value.map(function (item) {
      return resolveValue(item, ctx);
    });
  }
  if (value !== null && typeof value === 'object') {
    const resolved = {};
    for (const key in value) {
      resolved[key] = resolveValue(value[key], ctx);
    }
    return resolved;
  }
  return value;
}

function pickRow(meta) {
  const rows = datasets[meta.name];
  if (!rows || rows.length === 0) {
    exec.test.abort('dataset ' + meta.name + ' is empty');
    return {};
  }

  let index;
  if (meta.strategy === 'per_vu') {
    index = exec.vu.idInTest - 1;
  } else if (meta.strategy === 'random') {
    index = Math.floor(Math.random() * rows.length);
  } else if (meta.strategy === 'cycle') {
    index = exec.scenario.iterationInTest % rows.length;
  } else {
    index = exec.scenario.iterationInTest;
  }

  if (index >= rows.length) {
    if (meta.onExhausted === 'fail') {
      exec.test.abort('dataset ' + meta.name + ' exhausted');
      return {};
    }
    index = index % rows.length;
  }
  return rows[index];
}

function getByPath(value, path) {
  if (!path) {
    return undefined;
  }
  return path.split('.').reduce(function (current, key) {
    if (current === null || current === undefined) {
      return undefined;
    }
    return current[key];
  }, value);
}

function getHeader(headers, name) {
  if (!headers || !name) {
    return undefined;
  }
  if (headers[name] !== undefined) {
    return headers[name];
  }
  const lower = name.toLowerCase();
  for (const key in headers) {
    if (key.toLowerCase() === lower) {
      return headers[key];
    }
  }
  return undefined;
}

function applyOp(actual, op, expected, pattern) {
  if (op === 'exists') {
    return actual !== undefined && actual !== null && asString(actual) !== '';
  }
  if (op === 'regex') {
    return new RegExp(pattern).test(asString(actual));
  }
  if (op === 'contains') {
    return asString(actual).indexOf(asString(expected)) >= 0;
  }
  if (op === 'in') {
    if (!Array.isArray(expected)) {
      return false;
    }
    return expected.map(asString).indexOf(asString(actual)) >= 0;
  }
  if (op === 'gte') {
    return Number(actual) >= Number(expected);
  }
  if (op === 'lte') {
    return Number(actual) <= Number(expected);
  }
  const equal =
    actual !== undefined &&
    actual !== null &&
    asString(actual) === asString(expected);
  return op === 'ne' ? !equal : equal;
}

function evaluateCheck(res, rule, ctx) {
  let actual;
  if (rule.type === 'status') {
    actual = res.status;
  } else if (rule.type === 'json') {
    try {
      actual = getByPath(res.json(), rule.path);
    } catch (_error) {
      actual = undefined;
    }
  } else if (rule.type === 'header') {
    actual = getHeader(res.headers, rule.name);
  } else if (rule.type === 'body') {
    actual = res.body;
  }
  const expected = resolveValue(rule.value, ctx);
  return applyOp(actual, rule.op, expected, rule.pattern);
}

function runChecks(res, step, ctx) {
  let allPassed = true;
  const checks = step.checks || [];
  checks.forEach(function (rule, index) {
    const passed = evaluateCheck(res, rule, ctx);
    check(res, {
      [step.name + ':' + index]: function () {
        return passed;
      },
    });
    if (!passed) {
      allPassed = false;
      bizFailures.add(1);
    }
  });
  return allPassed;
}

function extractValue(res, rule) {
  if (rule.from === 'json') {
    try {
      return getByPath(res.json(), rule.path);
    } catch (_error) {
      return undefined;
    }
  }
  if (rule.from === 'header') {
    return getHeader(res.headers, rule.path);
  }
  if (rule.from === 'regex') {
    const match = new RegExp(rule.pattern).exec(res.body || '');
    if (!match) {
      return undefined;
    }
    const group = rule.group === undefined ? 1 : rule.group;
    return match[group];
  }
  return undefined;
}

function hasHeader(headers, name) {
  const lower = name.toLowerCase();
  for (const key in headers) {
    if (key.toLowerCase() === lower) {
      return true;
    }
  }
  return false;
}

function requestUrl(step, ctx) {
  const path = resolveString(step.path, ctx);
  if (path.indexOf('http://') === 0 || path.indexOf('https://') === 0) {
    return path;
  }
  return plan.baseUrl + path;
}

function requestBody(step, ctx, headers) {
  if (step.body === undefined || step.body === null) {
    return null;
  }
  const resolved = resolveValue(step.body, ctx);
  if (step.contentType === 'json') {
    if (!hasHeader(headers, 'Content-Type')) {
      headers['Content-Type'] = 'application/json';
    }
    return JSON.stringify(resolved);
  }
  if (step.contentType === 'form') {
    if (!hasHeader(headers, 'Content-Type')) {
      headers['Content-Type'] = 'application/x-www-form-urlencoded';
    }
    const pairs = [];
    for (const key in resolved) {
      pairs.push(
        encodeURIComponent(key) + '=' + encodeURIComponent(asString(resolved[key]))
      );
    }
    return pairs.join('&');
  }
  return asString(resolved);
}

export default function () {
  const ctx = {
    vars: {},
    data: {},
    env: {},
  };
  for (const key of plan.envKeys) {
    ctx.env[key] = __ENV[key] === undefined ? '' : __ENV[key];
  }
  for (const meta of plan.data) {
    const row = pickRow(meta);
    for (const key in row) {
      ctx.data[key] = row[key];
    }
  }

  for (const step of plan.steps) {
    const headers = resolveValue(step.headers || {}, ctx);
    const body = requestBody(step, ctx, headers);
    const res = http.request(step.method, requestUrl(step, ctx), body, {
      headers: headers,
      tags: { step: step.name },
    });

    const passed = runChecks(res, step, ctx);
    if (!passed) {
      if (step.onFailure === 'abort_test') {
        exec.test.abort('step ' + step.name + ' checks failed');
      }
      if (step.onFailure === 'abort_iteration') {
        return;
      }
    }

    for (const rule of step.extract || []) {
      const value = extractValue(res, rule);
      if (value === undefined) {
        bizFailures.add(1);
        if (step.onFailure === 'abort_test') {
          exec.test.abort('step ' + step.name + ' extract ' + rule.name + ' missing');
        }
        if (step.onFailure === 'abort_iteration') {
          return;
        }
        continue;
      }
      ctx.vars[rule.name] = value;
    }

    if (step.thinkTimeMs > 0) {
      sleep(step.thinkTimeMs / 1000);
    }
  }
}

export function handleSummary(data) {
  return {
    'summary.json': JSON.stringify(data),
  };
}
