import "server-only";
import { getApiBaseUrl } from "@/lib/api-base-url";
import { buildApiHeaders, readRequiredServerSession } from "@/lib/auth/server-route";
import { memoryProxy, type ProxyConfig } from "./proxy";
export function proxyMemoryRequest(request: Request, config: ProxyConfig) {
  return memoryProxy(request, config, { session: readRequiredServerSession, headers: buildApiHeaders, baseUrl: getApiBaseUrl(), fetch });
}
