// 登录页：微信一键登录入口（只保留登录 + 隐私协议勾选）
// 头像与昵称统一由「完善资料」页维护，这里不再收集，避免同一份资料有两个入口。
const { login } = require('../../utils/auth');

Page({
  data: {
    agreed: false,
    loading: false,
  },

  toggleAgree() {
    this.setData({ agreed: !this.data.agreed });
  },

  goPrivacy() {
    wx.navigateTo({ url: '/pages/privacy/privacy' });
  },

  async onLogin() {
    if (!this.data.agreed) {
      wx.showToast({ title: '请先阅读并同意隐私政策', icon: 'none' });
      return;
    }
    if (this.data.loading) return;
    this.setData({ loading: true });

    try {
      // 登录只带 code；头像昵称由「完善资料」页后续补充
      await login({ silent: false });
      wx.showToast({ title: '登录成功', icon: 'success' });
      // 统一回首页：登录页既可能是被守卫拦过来的，也可能是「退出登录」主动跳来的
      setTimeout(() => wx.reLaunch({ url: '/pages/index/index' }), 600);
    } catch (err) {
      // request 层已弹提示，这里只兜底
    } finally {
      this.setData({ loading: false });
    }
  },
});
