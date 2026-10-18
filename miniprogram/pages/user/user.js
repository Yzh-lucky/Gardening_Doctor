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

  goProfile() {
    wx.navigateTo({ url: '/pages/profile/profile' });
  },

  onLogout() {
    wx.showModal({
      title: '退出登录',
      content: '退出后需要重新登录才能查看诊断历史',
      confirmText: '退出',
      confirmColor: '#b23a31',
      success: (res) => {
        if (!res.confirm) return;
        clearToken();
        const app = getApp();
        if (app && app.globalData) {
          app.globalData.userInfo = null;
          app.globalData.quota = null;
        }
        // redirectTo 而不是 navigateTo：把会静默重登的「我的」页从栈里移除，
        // 否则返回时 onShow 会自动登录，退出动作等于白做
        wx.redirectTo({ url: '/pages/login/login' });
      },
    });
  },
});
