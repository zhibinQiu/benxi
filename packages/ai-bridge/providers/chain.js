const PROVIDER_CHAIN = [
  {
    key: 'qwen',
    name: '通义千问',
    url: 'https://tongyi.aliyun.com/qianwen/',
    authDomains: ['login.aliyun.com', 'signin.aliyun.com', 'aliyun.com/login'],
    tabHosts: ['tongyi.aliyun.com', 'qianwen.com'],
  },
  {
    key: 'kimi',
    name: 'Kimi',
    url: 'https://kimi.moonshot.cn/',
    authDomains: ['kimi.moonshot.cn/login', 'moonshot.cn/login'],
    tabHosts: ['kimi.moonshot.cn'],
  },
  {
    key: 'doubao',
    name: '豆包',
    url: 'https://www.doubao.com/chat/',
    authDomains: ['doubao.com/login', 'login.doubao.com'],
    tabHosts: ['doubao.com'],
  },
  {
    key: 'deepseek',
    name: 'DeepSeek',
    url: 'https://chat.deepseek.com/',
    authDomains: ['chat.deepseek.com/login', 'deepseek.com/login'],
    tabHosts: ['chat.deepseek.com'],
  },
];

module.exports = { PROVIDER_CHAIN };
