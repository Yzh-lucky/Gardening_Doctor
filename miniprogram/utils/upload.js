// 头像上传：wx.uploadFile 单文件 → POST /user/avatar
// 关键点：小程序上传接口返回的是字符串，必须手动 JSON.parse；
// Authorization 需手写 header（request.js 的 header 逻辑只适用于 wx.request）。
const { baseUrl, fileUrlPrefix, debug } = require('../config');
const { getToken, onUnauthorized } = require('./auth');

// 后端返回的是 /static/... 相对路径，而 avatar_url 按契约就是绝对 URL
// （API接口文档 2.1 示例为 https://thirdwx.qlogo.cn/xxx），
// 且小程序 <image> 无法加载 "/" 开头的服务端路径，所以在这里拼成绝对地址。
function toAbsolute(path) {
  return /^https?:\/\//.test(path) ? path : fileUrlPrefix + path;
}

function doUpload(filePath, retried) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: baseUrl + '/user/avatar',
      filePath,
      name: 'file',
      header: { Authorization: 'Bearer ' + getToken() },
      timeout: 20000,
      success(res) {
        let body = {};
        try {
          body = JSON.parse(res.data || '{}');
        } catch (e) {
          body = {};
        }
        if (body.code === 0 && body.data) {
          return resolve(toAbsolute(body.data.avatar_url));
        }
        // 登录态失效：不再静默重登，跳登录页并放弃本次上传
        if ((body.code === 1001 || body.code === 1002 || res.statusCode === 401) && !retried) {
          onUnauthorized();
          return reject(body);
        }
        if (debug) {
          console.warn('[upload] 头像上传失败', body.code, body.message, body.trace_id);
        }
        wx.showToast({ title: (body && body.message) || '头像上传失败', icon: 'none' });
        reject(body);
      },
      fail(err) {
        if (debug) {
          console.warn('[upload] 网络异常', err);
        }
        wx.showToast({ title: '网络异常，请重试', icon: 'none' });
        reject({ code: -1, message: '网络异常，请重试' });
      },
    });
  });
}

/**
 * 上传本地头像文件，resolve 服务端可持久化的 avatar_url
 * @param {string} filePath chooseAvatar 返回的本地临时路径（建议先压缩）
 * @returns {Promise<string>}
 */
function uploadAvatar(filePath) {
  return doUpload(filePath, false);
}

module.exports = { uploadAvatar };
