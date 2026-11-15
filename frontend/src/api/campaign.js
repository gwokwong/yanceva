import service from './index'

/**
 * 创建对比预演计划（克隆变体，不调用 LLM）
 * @param {Object} data - { name, base_simulation_id, variants: [{label, overrides}] }
 */
export const createCampaign = (data) => {
  return service.post('/api/campaign/create', data)
}

/**
 * 串行运行全部变体模拟（异步任务）
 * @param {string} campaignId
 */
export const runCampaign = (campaignId) => {
  return service.post(`/api/campaign/${campaignId}/run`)
}

/**
 * 查询 Campaign 详情（含变体实时状态）
 */
export const getCampaign = (campaignId) => {
  return service.get(`/api/campaign/${campaignId}`)
}

/**
 * Campaign 列表
 */
export const listCampaigns = () => {
  return service.get('/api/campaign/list')
}

/**
 * 市场指标对比（规则聚合，零 LLM）
 */
export const getCampaignComparison = (campaignId) => {
  return service.get(`/api/campaign/${campaignId}/comparison`)
}

/**
 * 生成 LLM 对比报告（单次调用）
 */
export const generateCampaignReport = (campaignId) => {
  return service.post(`/api/campaign/${campaignId}/report`)
}

/**
 * 删除 Campaign
 */
export const deleteCampaign = (campaignId) => {
  return service.delete(`/api/campaign/${campaignId}`)
}
