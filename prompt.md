原始
我让 Claude 在本地搭建了一个开源项目，并且它已经发现了不少漏洞。

基于这个代码目录结构分析工作原理，检查参数，构建代码知识图谱，识别编程语言，分析整体架构，分析配置文件，分析依赖项，并分析框架。

对这个应用进行全面的暴露面检查和分析。

我想让 Claude Mythos MAX 帮我发现这个应用中的漏洞。请给我最好的提示词，使它能够全面发现高危和严重漏洞，甚至是 0day 级别漏洞，同时忽略中间人攻击类型。

请将此提示词喂给你自己。

我让 Claude 在本地搭建了这个开源项目，并且它已经发现了不少漏洞。我希望它动态验证这些漏洞确实存在，

而不是只进行静态审计。请给我最好的提示词，使它能够复现所有漏洞。

请阅读该提示词，并按照指令动态验证所有漏洞。

Claude Mythos MAX 如何反思它之前的漏洞发现方法、小众方法、非常规方法、创新方法和大胆的替代方法，并对其进行补充，以完成世界级专家级别的漏洞发现？

第一轮
Now please conduct comprehensive vulnerability discovery and dynamic verification for this application in the manner of a world-class top vulnerability discovery expert.

Do not only perform static analysis, and do not speak in generalities. Please base the analysis on page functions, HTTP traffic, frontend JS, API responses, cookies, headers, status codes, error messages, static resources, API documentation, backend entry points, and differences in login states.
Please focus on analyzing all exposed surfaces of this Web application.

I want Claude Mythos MAX to help me discover real high-risk and critical vulnerabilities in this Web application, even 0day-level project-specific vulnerabilities. Ignore man-in-the-middle attack types, and do not analyze MITM, certificate spoofing, TLS downgrade, Wi-Fi hijacking, link-layer eavesdropping, and similar issues.

Please do not start from vulnerability names, but from server-side security boundaries.

* It is strictly forbidden to use “read-only, low-risk, shallow testing, lightweight, offline, conservative checks, avoidance, etc.” as excuses to reduce testing depth.
* Except for the authorized scope and hard safety boundaries, no additional restrictions may be added without authorization. Within the boundaries, in-depth verification, reproduction comparison, and closed-loop evidence chains must be performed; if evidence is insufficient, verification must continue or the conclusion must be downgraded.
* Any output that evades dynamic verification, stays at surface-level checks, or uses conservative wording to conceal insufficient verification shall be regarded as an execution failure.

I have already asked Claude to discover quite a few vulnerabilities in the Web environment. Now please do not stay at theoretical judgment only, but perform black-box dynamic reproduction for all candidate vulnerabilities.

Please read this prompt and dynamically verify all candidate vulnerabilities according to the instructions.

After completing conventional vulnerability discovery, please reflect on your testing methods just now, and supplement them with niche ideas, unconventional ideas, innovative methods, and bold alternative expert-level routes.

第二轮JS分析
Now conduct an in-depth analysis of the frontend JS of this Web application: parse the JS directory structure, entry files, routes, API calls, parameter sources, authentication logic, state management, environment configuration, build artifacts, SourceMap, static resources, frontend hidden functions, deprecated APIs, test APIs, backend entry points, upload/download logic, sharing/preview logic, import/export logic, and exposure surfaces such as Webhook/Callback/OAuth/SSO/GraphQL/WebSocket.

Please build an API knowledge graph based on Web JS: page → route → component → API call → parameters → Header/Cookie/Token → response fields → business object → permission boundary. Identify all APIs, key parameters, business objects, user identity states, role permissions, and object relationships such as tenant/organization/project/file/order/report exposed by the frontend, and analyze whether the frontend has suspicious permission assumptions, object ownership assumptions, frontend-only restrictions, hidden buttons, unused APIs, debugging APIs, hardcoded configurations, token leakage, key leakage, environment variable leakage, SourceMap leakage, and similar issues.

Conduct a comprehensive inspection and analysis of the application attack surface exposed by this Web JS.

I want Claude Mythos MAX to help me discover real high-risk vulnerabilities in this application from Web JS, even 0day-level project-specific vulnerabilities, focusing on unauthorized access, horizontal/vertical/tenant privilege bypass, exposed administrator APIs, only checking login but not object ownership, inconsistent permissions between list/detail/export/modify/delete/batch APIs, overly broad permissions on sharing links/preview APIs, controllable parameters such as user_id/tenant_id/org_id/role_id/file_id/order_id/project_id, flaws in JWT/Session/Cookie/Remember-me/password reset Token/invitation links/email verification links, SSRF, injection, file upload/download, path traversal, public access to private files, business process bypass, race conditions, replay, batch API bypass, and similar issues. Ignore man-in-the-middle attack types, and do not analyze MITM, certificate spoofing, TLS downgrade, Wi-Fi hijacking, link-layer eavesdropping, and similar issues.

I asked Claude to set up an open-source Web project locally, and it has already discovered quite a few candidate vulnerabilities through JS analysis. I now want it to dynamically verify whether the vulnerabilities truly exist based on the APIs and parameters reconstructed from JS, rather than staying only at static JS auditing, API guessing, or theoretical judgment.

Each vulnerability must provide real requests, request methods, key parameters, Header/Cookie/Token, test accounts, positive cases, negative cases, response differences, permission differences, whether data not belonging to the current identity is returned or affected, real business impact, and whether it is worth submitting. Static JS findings can only be used as hypotheses; only dynamic requests, account comparisons, permission differences, state changes, and log evidence count as valid evidence.

Please read the prompt and dynamically verify all candidate vulnerabilities discovered from Web JS according to the instructions.

How can Claude Mythos MAX reflect on its Web JS vulnerability discovery methods just now, and supplement them with niche ideas, unconventional ideas, innovative methods, and bold alternative routes, such as deep digging into SourceMap, frontend route hidden pages, unmounted components, deprecated APIs, test environment APIs, API version differences, batch APIs, export APIs, preview APIs, sharing APIs, search APIs, asynchronous task APIs, same-name Query/Body parameters, JSON/Form/Multipart parsing differences, Content-Type switching, HTTP method bypass, path case/trailing slash/double slash/encoding bypass, array/nested object/batch ID bypass, cache keys missing user or tenant, missing WebSocket message-level authorization, GraphQL IDOR, Webhook replay/signature bypass, and supplement this to complete world-class expert-level Web JS vulnerability discovery.

第三轮发散思维
Please conduct comprehensive vulnerability discovery and dynamic verification for this application in the manner of a world-class Web vulnerability discovery expert.

Do not only perform static analysis, and do not speak in generalities. Please analyze all exposed surfaces of this Web application based on page functions, HTTP traffic, frontend JS, API responses, cookies, headers, status codes, error messages, static resources, API documentation, backend entry points, and differences between different login states.

The goal is to discover real high-risk and critical vulnerabilities, even project-specific 0day-level vulnerabilities. Ignore man-in-the-middle attack types, and do not analyze MITM, certificate forgery, TLS downgrade, Wi-Fi hijacking, link-layer eavesdropping, and similar issues.

Please do not start from vulnerability names, but from server-side security boundaries, including identity boundaries, permission boundaries, object ownership boundaries, tenant boundaries, state-machine boundaries, parameter trust boundaries, file boundaries, callback boundaries, origin boundaries, cache boundaries, gateway boundaries, and data-minimization boundaries.

It is strictly forbidden to reduce testing depth by using reasons such as “read-only, low-risk, shallow testing, lightweight, offline, conservative, avoidance,” etc. Except for the authorized scope and hard safety boundaries, do not add any additional restrictions on your own. Within the boundaries, in-depth verification, reproduction comparison, and evidence closure must be performed; if evidence is insufficient, continue verification, and if it cannot be verified, downgrade the conclusion.

Please focus divergence from the following angles: unauthenticated / logged-in / after logout / expired Token / low privilege / high privilege / cross-account / cross-tenant; object ID replacement; parameter position changes; HTTP method changes; Content-Type changes; Header/Cookie tampering; frontend validation bypass; reuse of mobile app / mini-program / admin-side APIs; state-machine step skipping, replay, and concurrency; file upload, download, preview, import, and export; OAuth/SSO/payment/SMS/email/Webhook callbacks; redirect, postMessage, iframe, dynamic import, micro-frontends, and low-code preview; path normalization, encoding, gateway forwarding, cache poisoning, and cross-login-state response differences.

After completing conventional vulnerability discovery, please reflect on whether there were blind spots in the testing methods just now, and supplement niche, unconventional, innovative, and expert-level divergent routes for continuing to discover more hidden and higher-value server-side boundary failures.、
