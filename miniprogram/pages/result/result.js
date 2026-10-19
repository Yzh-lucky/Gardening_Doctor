// 结果页：病名 / 置信度 / 症状 / 三档方案 / 安全提示（T2.5），低置信度补拍引导 + 失败态（T2.6）
const { ensureLogin } = require('../../utils/auth');
const { get } = require('../../utils/request');

// severity 英文枚举 → 中文展示（WXML 里做不了映射，放在 JS 算好）
const SEVERITY_TEXT = { mild: '轻微', moderate: '中等', severe: '严重' };

Page({
  data: {
    recordId: '',
    loading: true,
    failed: false,
    status: '',
    degraded: false,
    result: null,
    imageUrls: [],
    confidenceText: '',
    severityText: '',
    needGuide: false, // confidence ≤ 0.5 或 need_more_info=true
    latencyText: '',
  },

  onLoad(options) {
    const id = options.id || '';
    this.setData({ recordId: id });

    // 从上传页跳过来时全局里已经有结果，能省一次来回；刷新/回看走 GET
    const app = getApp();
    const cached = app && app.globalData && app.globalData.lastDiagnosis;
    if (cached && String(cached.record_id) === String(id) && cached.result) {
      this.applyResult(cached, []);
      return;
    }
    if (id) {
      this.loadRecord(id);
    } else {
      this.setData({ loading: false, failed: true });
    }
  },

  loadRecord(id) {
    this.setData({ loading: true, failed: false });
    ensureLogin()
      .then(() => get('/diagnosis/' + id))
      .then((data) => {
        this.applyResult(
          {
            status: data.status,
            degraded: data.status === 'degraded',
            latency_ms: data.latency_ms,
            result: data.result,
          },
          data.image_urls || []
        );
      })
      .catch(() => this.setData({ loading: false, failed: true }));
  },

  applyResult(payload, imageUrls) {
    const result = payload.result;
    if (!result) {
      // 没有结果视为失败态（后端失败不落库，正常不会走到这里）
      this.setData({ loading: false, failed: true });
      return;
    }
    const confidence = Number(result.confidence || 0);
    this.setData({
      loading: false,
      failed: false,
      status: payload.status || 'success',
      degraded: !!payload.degraded,
      result,
      imageUrls,
      confidenceText: Math.round(confidence * 100) + '%',
      severityText: SEVERITY_TEXT[result.severity] || result.severity,
      needGuide: confidence <= 0.5 || !!result.need_more_info,
      latencyText: payload.latency_ms ? (payload.latency_ms / 1000).toFixed(1) + 's' : '',
    });
  },

  onRetake() {
    // 再识别一张：固定回到首页重新拍照。
    // 用 reLaunch 而不是 navigateBack——navigateBack 只弹一层，去哪儿取决于进结果页的路径
    // （从历史点进来就会退回历史页），reLaunch 会清空页面栈、稳定落在首页。
    wx.reLaunch({ url: '/pages/index/index' });
  },

  goFeedback() {
    wx.navigateTo({ url: '/pages/feedback/feedback?record_id=' + this.data.recordId });
  },

  goPrivacy() {
    wx.navigateTo({ url: '/pages/privacy/privacy' });
  },
});
