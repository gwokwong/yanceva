import service from './index'

/**
 * 商品目录（含 intake_schema，前端动态渲染提交表单）
 */
export const listProducts = (params = {}) => {
  return service.get('/api/orders/products', { params })
}

/**
 * 提交订单（FormData：product_id/user_email/title/payload/files[]）
 */
export const createOrder = (formData) => {
  return service.post('/api/orders', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

/**
 * 订单列表
 * @param {Object} params - { user_email, status, limit }
 */
export const listOrders = (params = {}) => {
  return service.get('/api/orders', { params })
}

/**
 * 订单详情
 */
export const getOrder = (orderId) => {
  return service.get(`/api/orders/${orderId}`)
}

/**
 * 支付订单（dev 模式直接入队；stripe 返回 checkout_url）
 */
export const payOrder = (orderId) => {
  return service.post(`/api/orders/${orderId}/pay`)
}

/**
 * 取消订单
 */
export const cancelOrder = (orderId) => {
  return service.post(`/api/orders/${orderId}/cancel`)
}

/**
 * 交付物下载地址
 */
export const deliverableUrl = (orderId) => {
  const base = service.defaults.baseURL || ''
  const email = localStorage.getItem('order_email') || ''
  return `${base}/api/orders/${orderId}/deliverable?email=${encodeURIComponent(email)}`
}
