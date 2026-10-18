// 图片处理：选择 → 压缩（≤2MB / 长边 ≤1280）→ 上传识别
// 关键点：小程序 wx.uploadFile 一次只能带一个文件，而 POST /diagnosis 要求 1–3 张图在**同一个请求**里，
// 所以这里改用 wx.request + JSON（图片转 base64）。后端两条路径都支持，见 routers/diagnosis.py。
const { baseUrl, debug } = require('../config');
const { getToken, login } = require('./auth');

const MAX_SIZE_MB = 2;
const MAX_COUNT = 3;

/** 选图：支持拍照与相册，最多 3 张 */
function chooseImages(count = 1, sourceType = ['camera', 'album']) {
  return new Promise((resolve, reject) => {
    wx.chooseMedia({
      count: Math.min(count, MAX_COUNT),
      mediaType: ['image'],
      sourceType,
      sizeType: ['compressed'],
      success: (res) => resolve(res.tempFiles.map((f) => ({ tempFilePath: f.tempFilePath, size: f.size }))),
      fail: reject,
    });
  });
}

/** 单张压缩：quality 70，大多数手机照片能压到 2MB 以内 */
function compressImage(src, quality = 70) {
  return new Promise((resolve) => {
    wx.compressImage({
      src,
      quality,
      success: (res) => resolve(res.tempFilePath),
      // 压缩失败不阻塞：直接用原图（后端还会二次校验大小）
      fail: () => resolve(src),
    });
  });
}

function getFileSize(filePath) {
  return new Promise((resolve) => {
    wx.getFileSystemManager().getFileInfo({
      filePath,
      success: (res) => resolve(res.size),
      fail: () => resolve(0),
    });
  });
}

/** 逐张压缩；如果压缩后仍超过 2MB，继续降质量重压 */
async function prepareImages(files) {
  const prepared = [];
  for (const file of files) {
    let path = await compressImage(file.tempFilePath, 70);
    let size = await getFileSize(path);
    if (size > MAX_SIZE_MB * 1024 * 1024) {
      path = await compressImage(file.tempFilePath, 40);
      size = await getFileSize(path);
    }
    prepared.push({ tempFilePath: path, size });
  }
  return prepared;
}

/** 读成 base64（同步接口在读大文件时会卡一下 UI，用异步版） */
function readAsBase64(filePath) {
  return new Promise((resolve, reject) => {
    wx.getFileSystemManager().readFile({
      filePath,
      encoding: 'base64',
      success: (res) => resolve(res.data),
      fail: reject,
    });
  });
}

/** 按后缀拼 data URL；后端按魔数校验，这里只是给模型正确的 MIME 提示 */
function toDataUrl(base64, filePath) {
  const ext = String(filePath || '').split('.').pop().toLowerCase();
  const mime = ext === 'png' ? 'image/png' : ext === 'webp' ? 'image/webp' : 'image/jpeg';
  return 'data:' + mime + ';base64,' + base64;
}

/** 真发一次请求；只在 token 失效时静默重登后重发一次（避免重复扣额度） */
function doRequest(payload, retried) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: baseUrl + '/diagnosis',
      method: 'POST',
      header: { 'content-type': 'application/json', Authorization: 'Bearer ' + getToken() },
      data: payload,
      timeout: 30000, // 识别链路较长，比普通的 20s 放宽
      success(res) {
        const body = res.data || {};
        // 5001 = 降级结果：仍然有完整结果，按成功处理，前端只多显示一个"降级"标识
        if (body.code === 0 || body.code === 5001) {
          return resolve(Object.assign({ degraded: body.code === 5001 }, body.data));
        }
        if ((body.code === 1001 || body.code === 1002) && !retried) {
          return login({ silent: true })
            .then(() => doRequest(payload, true))
            .then(resolve)
            .catch(reject);
        }
        if (debug) {
          console.warn('[image] 识别失败', body.code, body.message, body.trace_id);
        }
        reject(body);
      },
      fail(err) {
        if (debug) {
          console.warn('[image] 网络异常', err);
        }
        reject({ code: -1, message: '网络异常，请重试' });
      },
    });
  });
}

/**
 * 上传并发起识别（POST /diagnosis）
 * @param {Array<{tempFilePath:string}>} files 1–3 张压缩后的图片
 * @param {Object} [options] { plantHint }
 * @returns {Promise<Object>} data：{ record_id, status, degraded, latency_ms, remaining_quota, result }
 */
async function uploadDiagnosis(files, options = {}) {
  if (!files || !files.length) {
    throw { code: 2001, message: '请先选择图片' };
  }
  if (files.length > MAX_COUNT) {
    throw { code: 2003, message: '最多上传 ' + MAX_COUNT + ' 张图片' };
  }

  // 顺序读取，保证 images 数组顺序 = 用户选图顺序（结果页要按顺序展示原图）
  const images = [];
  for (const file of files) {
    const base64 = await readAsBase64(file.tempFilePath);
    images.push(toDataUrl(base64, file.tempFilePath));
  }

  return doRequest(
    {
      images,
      plant_hint: options.plantHint || '',
      client_ts: Date.now(),
    },
    false
  );
}

module.exports = {
  MAX_COUNT,
  MAX_SIZE_MB,
  chooseImages,
  compressImage,
  prepareImages,
  readAsBase64,
  uploadDiagnosis,
};
