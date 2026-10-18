// 统一请求封装：拼接 baseUrl、带 token、按业务码分流、401 自动续期并只重发一次
const { baseUrl, debug } = require('../config');

// 由 auth.js 注入续期函数，避免 request ↔ auth 互相 require 造成循环依赖
let reloginHandler = null;

function setReloginHandler(fn) {
  reloginHandler = fn;
}

function buildHeader(options) {
  const header = Object.assign({ 'content-type': 'application/json' }, options.header || {});
  const token = wx.getStorageSync('token');
  if (token && !options.noAuth) {
    header.Authorization = 'Bearer ' + token;
  }
  return header;
}

function toastError(body) {
  const message = (body && body.message) || '请求失败';
  wx.showToast({ title: message, icon: 'none' });
  // trace_id 留在控制台，方便前后端对日志
  if (debug && body && body.trace_id) {
    console.warn('[request] trace_id =', body.trace_id, 'code =', body.code);
  }
}

/**
 * @param {Object} options
 * @param {string} options.url        以 / 开头的路径，例如 '/quota'
 * @param {string} [options.method]   默认 GET
 * @param {Object} [options.data]
 * @param {number} [options.timeout]  默认 20000ms（识别链路单独设更长）
 * @param {boolean} [options.noAuth]  免鉴权接口可传 true
 */
function request(options) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: baseUrl + options.url,
      method: options.method || 'GET',
      data: options.data || {},
      timeout: options.timeout || 20000,
      header: buildHeader(options),
      success(res) {
        const body = res.data || {};
        if (body.code === 0) {
          return resolve(body.data);
        }
        // token 失效：静默重新登录后原样重发一次；_retried 标记防止无限递归
        const needRelogin = body.code === 1001 || body.code === 1002 || res.statusCode === 401;
        if (needRelogin && reloginHandler && !options._retried && !options.noAuth) {
          return reloginHandler()
            .then(() => request(Object.assign({}, options, { _retried: true })))
            .then(resolve)
            .catch(reject);
        }
        toastError(body);
        reject(body);
      },
      fail(err) {
        if (debug) {
          console.warn('[request] 网络异常', options.url, err);
        }
        wx.showToast({ title: '网络异常，请重试', icon: 'none' });
        reject(err);
      },
    });
  });
}

module.exports = {
  request,
  setReloginHandler,
  get: (url, data, options) => request(Object.assign({ url, method: 'GET', data }, options)),
  post: (url, data, options) => request(Object.assign({ url, method: 'POST', data }, options)),
};
