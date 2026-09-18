# GitLab 连接使用个人访问令牌

GitLab 集成连接归属于一个控制平面项目，同时绑定创建者的个人 GitLab 权限，不作为项目共享机器人身份。用户手动提交自部署 GitLab 地址和 Personal Access Token；控制平面调用 `/api/v4/user` 验证成功后才创建连接，不保存 GitLab 用户资料，并使用环境级集成密钥加密 Token 后落库。这样能够保持 GitLab 本身的个人权限边界，但用户离职、账号停用或 Token 失效后需要重新建立或认证连接。
