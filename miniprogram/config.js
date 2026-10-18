// 环境配置：开发阶段没有域名，直接用本机地址 + 开发者工具勾选"不校验合法域名"
// 上线前把 env 改成 'prod'，并把 prod 里的域名换成已备案域名（详见 API接口文档 1.1）
const env = 'dev';

const CONFIG = {
  dev: {
    baseUrl: 'http://127.0.0.1:8000/api/v1',
    // 图片资源域名前缀（后端静态目录，本地调试不受 downloadFile 域名限制）
    fileUrlPrefix: 'http://127.0.0.1:8000',
    debug: true,
  },
  prod: {
    baseUrl: 'https://api.example.com/api/v1',
    fileUrlPrefix: 'https://api.example.com',
    debug: false,
  },
};

module.exports = Object.assign({ env }, CONFIG[env]);
