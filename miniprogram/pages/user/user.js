const { ensureLogin, fetchProfile, login, clearToken } = require('../../utils/auth');

Page({
  data: {
    userInfo: null,
    quota: null,
  },

  onShow() {
    this.loadProfile();
  },

  loadProfile() {
    ensureLogin()
      .then(() => fetchProfile())
      .then((profile) => this.setData({ userInfo: profile, quota: profile.quota }))
      .catch(() => {});
  },

  onRelogin() {
    clearToken();
    login({ silent: false })
      .then(() => {
        wx.showToast({ title: '已重新登录', icon: 'success' });
        this.loadProfile();
      })
      .catch(() => {});
  },

  goHistory() {
    wx.navigateTo({ url: '/pages/history/history' });
  },

  goPrivacy() {
    wx.navigateTo({ url: '/pages/privacy/privacy' });
  },
});
