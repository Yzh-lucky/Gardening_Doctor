// 科普详情页：GET /diseases/{id}（免鉴权只读），展示完整知识与三档方案
const { get } = require('../../utils/request');

Page({
  data: {
    detail: null,
    loaded: false,
    error: '',
  },

  onLoad(options) {
    const id = options && options.id;
    if (!id) {
      this.setData({ loaded: true, error: '缺少病害 ID' });
      return;
    }
    get('/diseases/' + id, {}, { noAuth: true })
      .then((detail) => this.setData({ detail, loaded: true }))
      .catch((body) => this.setData({ loaded: true, error: (body && body.message) || '加载失败' }));
  },

  goIndex() {
    wx.reLaunch({ url: '/pages/index/index' });
  },
});
