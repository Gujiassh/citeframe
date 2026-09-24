export function modelSettingsRecovery(code: string | null, locale: "zh" | "en"): string | null {
  const en = locale === "en";
  switch (code) {
    case "model_secret_unavailable": return en ? "The saved key cannot be read. Re-enter the API key or reset this capability." : "无法读取已保存的密钥。请重新输入 API Key，或恢复此能力的默认配置。";
    case "model_encryption_unavailable": return en ? "Ask an administrator to configure the shared model encryption key on API and Worker." : "请管理员为 API 与 Worker 配置共用的模型加密密钥。";
    case "model_endpoint_invalid": return en ? "Check the model API base URL in settings." : "请检查设置中的模型 API 地址。";
    case "model_endpoint_denied": return en ? "Use a public HTTPS endpoint, or ask an administrator to approve this private origin." : "请使用公网 HTTPS 接口，或请管理员授权此私有地址。";
    case "model_key_required": return en ? "Enter an API key for this endpoint before saving." : "请为此接口地址输入 API Key 后再保存。";
    default: return null;
  }
}
