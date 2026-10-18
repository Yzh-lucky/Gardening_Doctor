Page({
  data: {
    updatedAt: '2026-10-17',
  },

  // 从个人中心/首页弹窗都能进来，返回时按栈自动回退
  onBack() {
    wx.navigateBack({ delta: 1 });
  },
});
