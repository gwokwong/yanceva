# 🚀 平台上线申请与配置清单

> 逐项照着办。每节开头标注【谁来做】和【预计耗时】。
> 「你要填的信息」汇总表在文末，全部填完后即可 `bash scripts/deploy.sh setup && start` 上线。

---

## 1. 域名购买【你自己，10 分钟】

| 项 | 建议 |
|---|---|
| 注册商 | Cloudflare（成本价无溢价）或 Namecheap |
| 域名建议 | 与品牌相关的 .com；避免数字/连字符 |
| 年费 | ~$10-15 |
| 隐私保护 | Cloudflare/Namecheap 免费 WhoIs 隐私，务必开启 |

**买完后不要急着改 DNS**——先完成 §4 Cloudflare 配置。

✅ 购买后填写：`域名 = ____________`

## 2. VPS 服务器采购【你自己，15 分钟】

| 项 | 建议配置 |
|---|---|
| 地区 | 客户在海外 → **香港/新加坡/美西**（无需 ICP 备案） |
| 规格 | 2C4G 起步（无 GPU 需求，重活全在 DeepSeek 云端） |
| 系统 | Ubuntu 24.04 LTS |
| 供应商 | Vultr / Linode / Hetzner / 阿里云国际 |
| 费用 | $6-20/月 |

安装清单（服务器上执行）：

```bash
# Docker
curl -fsSL https://get.docker.com | sh
# uv（Python 包管理）
curl -LsSf https://astral.sh/uv/install.sh | sh
# Node 20+
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
# 项目代码
git clone <你的仓库> && cd MiroFish
```

✅ 采购后填写：`服务器 IP = ____________`、`SSH 登录方式 = ____________`

## 3. Creem 支付账号申请【你自己，1-3 天审核】

个人可申请，**无需海外公司**。审核较严，资料准备充分一次过。

### 申请资料准备

| 资料 | 说明 |
|---|---|
| 身份证件 | 身份证/护照照片（KYC） |
| 联系地址 | 真实地址（英文填写） |
| 收款方式 | 支付宝（直提人民币）或银行账户 |
| 产品说明 | 下面的表格直接照抄 |
| 网站 | 域名上线后再填（可先跳过，审核后补） |

### 申请步骤

1. 访问 creem.io → Sign up（邮箱注册）
2. 完成个人 KYC 认证
3. 创建 Products（逐条照抄下表，价格自行调整）
4. 配置 Webhook：Developers → Webhooks → 添加 `https://你的域名/api/orders/creem/webhook`，事件勾选 `checkout.completed`，记下 `whsec_` 签名密钥
5. 记下 API Key（Settings → API Keys）

### Creem Products 创建信息（直接复制）

| # | Product Name | Price | Description |
|---|---|---|---|
| 1 | E-commerce Launch Rehearsal · Standard | $49 | 40 simulated buyers/KOLs/competitors/media agents, 48-hour market rollout. Delivers buyer reaction, review risks, competitor response and conversion-friction report. |
| 2 | E-commerce Launch Rehearsal · Professional | $99 | 60 agents × 96-hour deep rollout + 2 A/B variants. Includes an explicit comparison verdict on which variant wins. |
| 3 | SaaS Pricing / Redesign Sandbox | $99 | 60 agents rehearse your pricing change or major redesign: churn risk, acceptance analysis, competitor poaching response. |
| 4 | Brand Crisis Response Rehearsal | $99 | 60 agents rehearse crisis spread and response effectiveness: script A/B, timing choice, second-wave warnings. |
| 5 | Cross-border Listing Risk Review | $19 | 5 market & compliance reviewers audit your listing: cultural sensitivities, regulatory risks, copy rewrites. ~5 min delivery. |
| 6 | Competitor Launch Response Sandbox | $99 | 60 agents rehearse your competitor's launch shockwave: churn risk, response-action effectiveness, KOL and channel attitudes. |
| 7 | Creator Content Risk Rehearsal | $29 | 60 agents rehearse the release of your episode: churn risk, controversy points, brand-safety flags, alternative wording. |

### 每个 Product 创建后，把 prod_xxx 填进 catalog.json

```bash
# 服务器上编辑 backend/uploads/products/catalog.json
# 每个 SKU 的 "creem_product_id": "prod_xxxxxxxx"（对应上表）
```

⚠️ **价格同步提醒**：Creem Checkout 的实际扣款金额以 Creem 后台的 Product 价格为准，
catalog.json 里的 `price_cents` 仅用于展示。两边必须保持一致，改价时两处同步修改。

✅ 申请后填写：`CREEM_API_KEY = ____________`、`CREEM_WEBHOOK_SECRET = ____________`、6 个 `prod_xxx = ____________`

## 4. Cloudflare 配置【你自己，20 分钟】

1. 域名 DNS 托管到 Cloudflare（免费计划）
2. DNS 记录：
   - `A` 记录：`@` → 服务器 IP（开启橙色云朵代理=免费 CDN+SSL）
   - `A` 记录：`www` → 服务器 IP
3. SSL/TLS 模式：**Full (strict)** 或 Flexible（先用 Flexible 最快通）
4. 全站 HTTPS 自动生效，无需 certbot

## 5. DeepSeek API【已有 ✅】

- 现有 key 可直接用于生产（建议在 DeepSeek 后台单独建一个生产用 key 便于额度管理）
- 充值建议：首月预演量预估 × ¥10/单，预留 ¥200-500
- 注意：DeepSeek 无 embedding 接口——embedding 已由本地 Ollama 承担，无需额外付费

## 6. 邮件交付通知【可选，10 分钟】

当前交付 = 站内下载。若要邮件通知（推荐，提升体验）：

1. 注册 [Resend](https://resend.com)（免费 100 封/天）→ 获取 API Key
2. 域名验证（加 DNS 记录）
3. `RESEND_API_KEY` 填入 .env（worker 发信功能为 Phase 2 预留，当前可手动邮件）

## 7. 生产 .env 完整模板【汇总所有填写项】

```bash
# ===== LLM =====
LLM_API_KEY=sk-____________
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL_NAME=deepseek-chat
LLM_MAX_OUTPUT_TOKENS=8192

# ===== 图谱 =====
NEO4J_URI=bolt://neo4j:7687        # 容器内部署用服务名
NEO4J_USER=neo4j
NEO4J_PASSWORD=<强密码，与 compose 一致>

# ===== Embedding =====
EMBEDDING_API_KEY=ollama
EMBEDDING_BASE_URL=http://ollama:11434/v1   # 容器内部署用服务名
EMBEDDING_MODEL_NAME=qwen3-embedding:0.6b
EMBEDDING_DIM=1024

# ===== 支付 =====
PAYMENT_MODE=creem
CREEM_API_KEY=____________
CREEM_WEBHOOK_SECRET=____________
PAYMENT_SUCCESS_URL=https://你的域名/orders?paid=1
# 不要配置 ALLOW_DEV_PAYMENT！
# STRIPE_API_KEY / STRIPE_WEBHOOK_SECRET （仅 stripe 模式）

# ===== 站点 =====
CORS_ORIGINS=https://你的域名
ADMIN_KEY=<随机长串，运维查询用>

# ===== Worker =====
WORKER_CONCURRENCY=1
WORKER_POLL_INTERVAL=5
```

## 8. 上线执行【30 分钟】

```bash
# 服务器上
bash scripts/deploy.sh setup      # 环境+容器+依赖+构建+测试+冒烟
bash scripts/deploy.sh start      # 启动 API + Worker

# 验证清单（逐项打勾）
curl https://你的域名/health                                    # {"status":"ok"}
curl https://你的域名/api/orders/products                      # 7 个 SKU
# 浏览器打开 https://你的域名/                                  # 落地页（英/中切换）
# 提交一笔真实订单 → Creem 扫码支付 → webhook 入队 → worker 执行 → 下载报告
```

## 9. 你要填的信息汇总（打勾清单）

- [ ] 域名：____________
- [ ] 服务器 IP：____________
- [ ] NEO4J_PASSWORD：____________
- [ ] CREEM_API_KEY：____________
- [ ] CREEM_WEBHOOK_SECRET：____________
- [ ] Creem prod_xxx × 7：____________
- [ ] DEEPSEEK 生产 key：____________
- [ ] ADMIN_KEY（随机长串）：____________
- [ ] PAYMENT_SUCCESS_URL：https://______/orders?paid=1
- [ ] CORS_ORIGINS：https://______

## 10. 上线后 30 天运营提示

- 监控：`bash scripts/deploy.sh status`（订单队列）+ `tail backend/uploads/run/worker.log`
- 备份：cron 每日 `cp orders.db orders.db.bak.$(date +%F)` + `uploads/` 打包
- 收集前 10 个真实订单的反馈，用于调校场景包 prompt（行业专业度是复购关键）
- Creem 提现周期：每月 1/15 日打款，支付宝到账
