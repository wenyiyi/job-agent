# job-agent

基于 LangChain 的远程职位查询 Agent，通过 FastAPI 提供 HTTP 接口。

## 本地运行

在项目根目录、激活虚拟环境后执行：

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

在本地 `.env` 中配置模型凭据（例如 `GOOGLE_API_KEY`）。`.env` 已被 Git 忽略，请勿提交。

接口文档：http://127.0.0.1:8000/docs

## 查询 Agent

```bash
curl -X POST http://127.0.0.1:8000/api/agent \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Find senior backend engineer jobs that hire worldwide."}'
```

成功响应：

```json
{"answer":"Agent 返回的职位推荐文本"}
```

接口等待 Agent 执行完成后返回最终文本，不返回内部工具调用消息。
`prompt` 去掉首尾空白后必须为 1–10000 个字符。参数不合法返回 422；
Agent 调用失败或没有返回文本时返回 502。当前接口未配置身份认证，默认本地运行。

## 测试

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

接口测试模拟 Agent 返回值，不调用真实模型或职位 API。
