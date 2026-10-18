// 登录相关：wx.login → POST /auth/login → 存 token；并发调用只会打一次登录接口
const { post, request, setReloginHandler, get } = require('./request');

const TOKEN_KEY = 'token';

let loginPromise = null;

function getToken() {
  return wx.getStorageSync(TOKEN_KEY) || '';
}

function setToken(token) {
  wx.setStorageSync(TOKEN_KEY, token);
}

function clearToken() {
  wx.removeStorageSync(TOKEN_KEY);
}

function wxLogin() {
  return new Promise((resolve, reject) => {
    wx.login({
      success(res) {
        // code 是一次性的，拿不到就必须重新调用，不能复用
        if (res.code) {
          resolve(res.code);
        } else {
          reject(new Error('wx.login 未返回 code'));
        }
      },
      fail: reject,
    });
  });
}

/**
 * 登录（含静默登录）
 * @param {Object} [options]
 * @param {boolean} [options.silent] 静默登录不弹 loading
 * @param {Object}  [options.profile] { nickname, avatar_url }
 */
function login(options = {}) {
  if (loginPromise) {
    return loginPromise; // 并发去重：同时在多个页面触发时只发一次请求
  }

  if (!options.silent) {
    wx.showLoading({ title: '登录中', mask: true });
  }

  loginPromise = wxLogin()
    .then((code) => post('/auth/login', Object.assign({ code }, options.profile || {}), { noAuth: true }))
    .then((data) => {
      setToken(data.token);
      const app = getApp();
      if (app && app.globalData) {
        app.globalData.userInfo = data.user;
      }
      return data;
    })
    .catch((err) => {
      // 微信凭证失效（1101）等情况下清掉旧 token，下次进入再重新登录
      clearToken();
      throw err;
    })
    .finally(() => {
      loginPromise = null;
      if (!options.silent) {
        wx.hideLoading();
      }
    });

  return loginPromise;
}

/** 保证已登录：有 token 直接用，没有就登录 */
function ensureLogin() {
  return getToken() ? Promise.resolve(getToken()) : login({ silent: true }).then((d) => d.token);
}

function fetchProfile() {
  return get('/user/profile');
}

function updateProfile(payload) {
  return request({ url: '/user/profile', method: 'PUT', data: payload });
}

// token 失效时，request 模块通过这个回调触发静默续期
setReloginHandler(() => login({ silent: true }));

module.exports = {
  TOKEN_KEY,
  getToken,
  setToken,
  clearToken,
  login,
  ensureLogin,
  fetchProfile,
  updateProfile,
};
