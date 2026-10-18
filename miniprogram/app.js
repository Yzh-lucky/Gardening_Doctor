const { login } = require('./utils/auth');

App({
  globalData: {
    userInfo: null,
    quota: null,
  },

  onLaunch() {
    // 静默登录：失败不阻塞启动，页面 onShow 时会再兜底一次
    login({ silent: true }).catch((err) => {
      console.warn('[app] 静默登录失败', err);
    });
  },
});
