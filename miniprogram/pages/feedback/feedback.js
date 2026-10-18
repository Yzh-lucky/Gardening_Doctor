// 反馈页（T3.2）：POST /feedback
// type=wrong 时后端会把记录状态置为 corrected，形成纠错闭环
const { ensureLogin } = require('../../utils/auth');
const { post } = require('../../utils/request');

Page({
  data: {
    recordId: '',
    type: 'wrong',
    correctName: '',
    comment: '',
    submitting: false,
  },

  onLoad(options) {
    this.setData({ recordId: (options && options.record_id) || '' });
  },

  onTypeChange(e) {
    this.setData({ type: e.detail.value });
  },

  onCorrectNameInput(e) {
    this.setData({ correctName: e.detail.value });
  },

  onCommentInput(e) {
    this.setData({ comment: e.detail.value });
  },

  onSubmit() {
    const { recordId, type, correctName, comment, submitting } = this.data;
    if (submitting) return;
    if (!recordId) {
      wx.showToast({ title: '缺少记录 ID，请从结果页进入', icon: 'none' });
      return;
    }

    this.setData({ submitting: true });
    ensureLogin()
      .then(() =>
        post('/feedback', {
          record_id: Number(recordId),
          type,
          // 只有"识别错误"才带病名，其他类型传 null，避免脏数据
          correct_name: type === 'wrong' ? correctName.trim() || null : null,
          comment: comment.trim() || null,
        })
      )
      .then(() => {
        wx.showToast({ title: '感谢反馈', icon: 'success' });
        setTimeout(() => wx.navigateBack({ delta: 1 }), 800);
      })
      .catch(() => {}) // 失败提示由 utils/request 统一 toast
      .then(() => this.setData({ submitting: false }));
  },
});
