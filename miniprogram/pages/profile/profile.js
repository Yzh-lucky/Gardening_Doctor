// 资料完善页：编辑头像与昵称，复用 fetchProfile 回填、updateProfile 保存
const { ensureLogin, fetchProfile, updateProfile } = require('../../utils/auth');
const { uploadAvatar } = require('../../utils/upload');
const { compressImage } = require('../../utils/image');

Page({
  data: {
    nickname: '',
    avatarUrl: '',
    avatarTempPath: '',
    loading: true,
    saving: false,
  },

  onLoad() {
    ensureLogin()
      .then(() => fetchProfile())
      .then((profile) => {
        this.setData({
          nickname: profile.nickname || '',
          avatarUrl: profile.avatar_url || '',
          loading: false,
        });
      })
      .catch(() => this.setData({ loading: false }));
  },

  onChooseAvatar(e) {
    this.setData({ avatarTempPath: (e.detail && e.detail.avatarUrl) || '' });
  },

  onNicknameInput(e) {
    this.setData({ nickname: (e.detail.value || '').trim() });
  },

  async onSave() {
    if (!this.data.nickname) {
      wx.showToast({ title: '请填写昵称', icon: 'none' });
      return;
    }
    if (this.data.saving) return;
    this.setData({ saving: true });

    try {
      const payload = { nickname: this.data.nickname };
      // 只有用户重新选了头像才上传，避免每次保存都多写一份文件
      if (this.data.avatarTempPath) {
        const small = await compressImage(this.data.avatarTempPath, 70);
        payload.avatar_url = await uploadAvatar(small);
      }

      await updateProfile(payload);
      const app = getApp();
      if (app && app.globalData) {
        // 让下次进个人中心时重新拉取，避免展示旧昵称头像
        app.globalData.userInfo = null;
      }
      wx.showToast({ title: '已保存', icon: 'success' });
      setTimeout(() => wx.navigateBack({ delta: 1 }), 600);
    } catch (err) {
      // request / upload 层已弹提示，这里只兜底
    } finally {
      this.setData({ saving: false });
    }
  },
});
