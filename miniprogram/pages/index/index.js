const { ensureLogin, fetchProfile } = require('../../utils/auth');
const { get } = require('../../utils/request');
const imageUtil = require('../../utils/image');

const PRIVACY_AGREED_KEY = 'privacy_agreed';
const DISEASE_PREVIEW_COUNT = 5; // 首页科普卡片只展示前几条，避免把首页撑长

Page({
  data: {
    quota: null,
    picked: [],
    ready: false,
    plantHint: '',
    recognizing: false,
    // T3.8：隐私授权弹窗。未同意前不放行拍照/相册（合规要求）
    privacyAgreed: false,
    showPrivacy: false,
    // 科普卡片：GET /diseases（免鉴权只读）
    diseases: [],
    diseasesLoaded: false,
  },

  onLoad() {
    this.setupPrivacy();
    this.loadDiseases();
  },

  // 首页科普卡片：拉前 5 条科普条目；免鉴权，失败也不阻塞首页其它区域
  loadDiseases() {
    get('/diseases', { page: 1, page_size: DISEASE_PREVIEW_COUNT }, { noAuth: true })
      .then((data) => this.setData({ diseases: data.list || [], diseasesLoaded: true }))
      .catch(() => this.setData({ diseasesLoaded: true }));
  },

  goDisease(e) {
    wx.navigateTo({ url: '/pages/disease/disease?id=' + e.currentTarget.dataset.id });
  },

  // 优先走微信官方隐私接口判断是否需要授权，取不到再退回本地记录
  setupPrivacy() {
    if (wx.getStorageSync(PRIVACY_AGREED_KEY) === '1') {
      this.setData({ privacyAgreed: true });
      return;
    }
    if (wx.getPrivacySetting) {
      wx.getPrivacySetting({
        success: (res) => this.setData({ showPrivacy: !!res.needAuthorization }),
        fail: () => this.setData({ showPrivacy: true }),
      });
    } else {
      this.setData({ showPrivacy: true });
    }
  },

  onAgreePrivacy() {
    wx.setStorageSync(PRIVACY_AGREED_KEY, '1');
    this.setData({ privacyAgreed: true, showPrivacy: false });
  },

  onRejectPrivacy() {
    this.setData({ showPrivacy: false });
    wx.showToast({ title: '未同意隐私政策，暂不能使用拍照识别', icon: 'none' });
  },

  openPrivacy() {
    wx.navigateTo({ url: '/pages/privacy/privacy' });
  },

  onShow() {
    this.loadProfile();
  },

  // 拉取用户信息与今日额度（API接口文档 3.3）
  loadProfile() {
    ensureLogin()
      .then(() => fetchProfile())
      .then((profile) => {
        const app = getApp();
        if (app && app.globalData) {
          app.globalData.userInfo = profile;
          app.globalData.quota = profile.quota;
        }
        this.setData({ quota: profile.quota });
      })
      .catch(() => {
        // 登录/资料失败不阻塞首页；额度区域保持空
      });
  },

  onChooseCamera() {
    this.pickImages(['camera']);
  },

  onChooseAlbum() {
    this.pickImages(['album']);
  },

  pickImages(sourceType) {
    // 未同意隐私政策前不放行相册/相机权限申请
    if (!this.data.privacyAgreed) {
      this.setData({ showPrivacy: true });
      return;
    }
    imageUtil
      .chooseImages(imageUtil.MAX_COUNT, sourceType)
      .then((files) => imageUtil.prepareImages(files))
      .then((prepared) => {
        this.setData({ picked: prepared, ready: prepared.length > 0 });
      })
      .catch(() => {
        // 用户取消选图，静默处理
      });
  },

  onRemovePicked(e) {
    const index = e.currentTarget.dataset.index;
    const picked = this.data.picked.slice();
    picked.splice(index, 1);
    this.setData({ picked, ready: picked.length > 0 });
  },

  onHintInput(e) {
    this.setData({ plantHint: e.detail.value });
  },

  // T2.2：压缩后一次性上传全部图片 → 识别 → 跳结果页
  onStartDiagnosis() {
    if (this.data.recognizing || !this.data.picked.length) {
      return;
    }
    this.setData({ recognizing: true });
    wx.showLoading({ title: 'AI 识别中…', mask: true });

    imageUtil
      .uploadDiagnosis(this.data.picked, { plantHint: this.data.plantHint.trim() })
      .then((data) => {
        wx.hideLoading();
        // 先把结果塞进全局缓存，结果页可秒渲染；结果页仍会用 GET /diagnosis/{id} 兜底
        const app = getApp();
        if (app && app.globalData) {
          app.globalData.lastDiagnosis = data;
        }
        // 识别成功会消耗一次额度，本地先把额度更新掉，避免返回首页时数字不及时
        if (typeof data.remaining_quota === 'number') {
          this.setData({ quota: Object.assign({}, this.data.quota, { remaining: data.remaining_quota }) });
        }
        wx.navigateTo({ url: '/pages/result/result?id=' + data.record_id });
      })
      .catch((body) => {
        wx.hideLoading();
        // 额度用完顺手刷新一下额度卡片，让用户看到剩余为 0
        if (body && body.code === 3001) {
          this.loadProfile();
        }
        wx.showToast({ title: (body && body.message) || '识别失败，请重试', icon: 'none' });
      })
      .then(() => this.setData({ recognizing: false }));
  },

  goHistory() {
    wx.navigateTo({ url: '/pages/history/history' });
  },

  goUser() {
    wx.navigateTo({ url: '/pages/user/user' });
  },
});
