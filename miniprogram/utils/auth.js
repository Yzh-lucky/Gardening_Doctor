// 登录相关：wx.login → POST /auth/login → 存 token；并发调用只会打一次登录接口
const { post, request, setReloginHandler, get } = require('./request');

const TOKEN_KEY = 'token';

let loginPromise = null;
// 防重入：同一时刻有多个请求发现未登录时，只跳一次登录页
let redirecting = false;

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

/**
 * 未登录 / 登录失效时统一跳登录页。
 * 用 reLaunch 而不是 navigateTo：清空页面栈，避免用户按返回又回到需要登录的页面。
 */
function redirectToLogin() {
  if (redirecting) return;
  redirecting = true;
  wx.reLaunch({
    url: '/pages/login/login',
    complete() {
      // 稍作延迟再解锁，避免同一时刻的多个请求重复触发跳转
      setTimeout(() => {
        redirecting = false;
      }, 800);
    },
  });
}

/** 登录态失效的统一处理：清掉旧 token + 跳登录页（不再静默续期） */
function onUnauthorized() {
  clearToken();
  redirectToLogin();
}

/**
 * 保证处于登录态：有 token 直接放行；没有则跳登录页并 reject。
 * 不采用静默登录后，所有调用 ensureLogin 的页面都会被这个守卫拦住。
 */
function ensureLogin() {
  const token = getToken();
  if (token) {
    return Promise.resolve(token);
  }
  redirectToLogin();
  return Promise.reject({ code: 1001, message: '请先登录' });
}

function fetchProfile() {
  return get('/user/profile');
}

function updateProfile(payload) {
  return request({ url: '/user/profile', method: 'PUT', data: payload });
}

// token 失效时，request 模块通过这个回调通知我们：不再静默续期，直接跳登录页。
// 返回 rejected promise，让 request.js 的 .catch 接住本次请求，不再重发。
setReloginHandler(() => {
  onUnauthorized();
  return Promise.reject({ code: 1001, message: '登录已过期，请重新登录' });
});

module.exports = {
  TOKEN_KEY,
  getToken,
  setToken,
  clearToken,
  login,
  ensureLogin,
  redirectToLogin,
  onUnauthorized,
  fetchProfile,
  updateProfile,
};
