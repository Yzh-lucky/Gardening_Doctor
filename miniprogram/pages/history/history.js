// 历史列表页（T3.1）：GET /diagnosis 分页 + 下拉刷新 + 触底加载
// 点条目直接进结果页看详情——回看和历史详情用同一套渲染，天然保证"数据与结果页一致"
const { ensureLogin } = require('../../utils/auth');
const { get } = require('../../utils/request');
const { fileUrlPrefix } = require('../../config');

const PAGE_SIZE = 20;

const STATUS_TEXT = {
  created: '待识别',
  recognizing: '识别中',
  success: '识别成功',
  degraded: '降级结果',
  failed: '识别失败',
  corrected: '已纠错',
};

// 后端返回的是 /static/2026/10/xxx.png 相对路径，小程序 image 组件要绝对地址
function absUrl(path) {
  if (!path) return '';
  return /^https?:\/\//.test(path) ? path : fileUrlPrefix + path;
}

// 2026-10-17T12:03:00+08:00 → 10-17 12:03（列表够用，不需要秒和时区）
function formatTime(iso) {
  if (!iso || iso.length < 16) return iso || '';
  return iso.slice(5, 16).replace('T', ' ');
}

function mapItem(item) {
  const urls = item.image_urls || [];
  return Object.assign({}, item, {
    thumbnailUrl: absUrl(item.thumbnail || urls[0]),
    statusText: STATUS_TEXT[item.status] || item.status,
    confidenceText: item.confidence == null ? '' : Math.round(item.confidence * 100) + '%',
    timeText: formatTime(item.created_at),
  });
}

Page({
  data: {
    records: [],
    page: 1,
    total: 0,
    hasMore: false,
    loading: false,
    loadingMore: false,
    loaded: false,
  },

  onShow() {
    // 每次进页面都重拉第一页：刚在结果页纠错过，回来能立刻看到状态变化
    this.loadFirstPage();
  },

  onPullDownRefresh() {
    this.loadFirstPage(() => wx.stopPullDownRefresh());
  },

  onReachBottom() {
    this.loadMore();
  },

  loadFirstPage(done) {
    if (this.loading) return;
    this.setData({ loading: true });
    ensureLogin()
      .then(() => get('/diagnosis', { page: 1, page_size: PAGE_SIZE }))
      .then((data) => this.applyPage(data, false))
      .catch(() => {})
      .then(() => {
        this.setData({ loading: false });
        if (done) done();
      });
  },

  loadMore() {
    if (!this.data.hasMore || this.data.loading || this.data.loadingMore) return;
    this.setData({ loadingMore: true });
    ensureLogin()
      .then(() => get('/diagnosis', { page: this.data.page + 1, page_size: PAGE_SIZE }))
      .then((data) => this.applyPage(data, true))
      .catch(() => {})
      .then(() => this.setData({ loadingMore: false }));
  },

  applyPage(data, append) {
    const list = (data.list || []).map(mapItem);
    this.setData({
      records: append ? this.data.records.concat(list) : list,
      page: data.page || 1,
      total: data.total || 0,
      hasMore: !!data.has_more,
      loaded: true,
    });
  },

  goDetail(e) {
    wx.navigateTo({ url: '/pages/result/result?id=' + e.currentTarget.dataset.id });
  },

  goIndex() {
    wx.reLaunch({ url: '/pages/index/index' });
  },
});
