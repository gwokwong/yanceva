/**
 * 临时存储待上传的文件和需求
 * 用于首页点击启动引擎后立即跳转，在Process页面再进行API调用
 */
import { reactive } from 'vue'

const state = reactive({
  files: [],
  simulationRequirement: '',
  scenario: 'public_opinion',
  isPending: false
})

export function setPendingUpload(files, requirement, scenario = 'public_opinion') {
  state.files = files
  state.simulationRequirement = requirement
  state.scenario = scenario
  state.isPending = true
}

export function getPendingUpload() {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    scenario: state.scenario,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.scenario = 'public_opinion'
  state.isPending = false
}

export default state
