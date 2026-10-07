import { Button, Modal, Typography } from 'antd'
import { useState } from 'react'

export function ZentaoMcpDeploymentHelp() {
  const [open, setOpen] = useState(false)
  return <>
    <Button type="link" onClick={() => setOpen(true)}>部署说明</Button>
    <Modal title="ZenTao-MCP 手动部署说明" open={open} onCancel={() => setOpen(false)} footer={null} width={800}>
      <div style={{ maxHeight: '65vh', overflow: 'auto', overflowWrap: 'anywhere' }}>
        <Typography.Paragraph>推荐每个项目部署一个 MCP 容器。平台只保存连接地址，不会启动、重启或停止容器。部署环境需要 Docker 和 Docker Compose，模板直接使用已发布镜像。</Typography.Paragraph>
        <ol>
          <li>获取仓库 <Typography.Text code>deploy/zentao-mcp/</Typography.Text> 中的 Compose、配置示例和说明，为每个项目复制到独立部署目录。</li>
          <li>首次部署时准备配置：
            <Typography.Paragraph code style={{ whiteSpace: 'pre-wrap' }}>{'mkdir -p config\ncp config.example.yaml config/config.yaml'}</Typography.Paragraph>
          </li>
          <li>编辑 <Typography.Text code>config/config.yaml</Typography.Text> 中的禅道 API 地址与对外实例地址；在 <Typography.Text code>compose.yaml</Typography.Text> 设置独立名称、端口及网络。部署文件无需 Token。</li>
          <li>在部署目录手动拉取镜像并启动：
            <Typography.Paragraph code style={{ whiteSpace: 'pre-wrap' }}>{'docker compose pull\ndocker compose up -d\ndocker compose ps'}</Typography.Paragraph>
          </li>
          <li>填写平台后端可访问的 MCP 地址，然后成员分别保存自己的 Token。</li>
        </ol>
        <Typography.Paragraph>后端直接运行在同一宿主机时，例如 <Typography.Text code>http://127.0.0.1:9091/zentao/mcp</Typography.Text>。后端与 MCP 在同一 Docker 网络时，例如 <Typography.Text code>http://mtx-zentao-project-a:9090/zentao/mcp</Typography.Text>；容器中的 127.0.0.1 指向容器自身。</Typography.Paragraph>
        <Typography.Paragraph>多个项目使用不同部署标识、配置和宿主机端口。修改 MCP 上游配置后手动重启相应容器；日常绑定、推送和 Token 更新无需重启。</Typography.Paragraph>
        <Typography.Paragraph type="secondary">完整配置、多项目示例及排障说明位于仓库 <Typography.Text code>docs/control-plane/zentao-mcp-deployment.md</Typography.Text>。</Typography.Paragraph>
      </div>
    </Modal>
  </>
}
