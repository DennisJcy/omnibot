# npm令牌配置指南

## 1. 准备npm scope

这些包使用 `@omniaibot/*` 作用域发布，因此 npm 上必须存在名为 `omniaibot` 的用户或组织，并且发布令牌所属账号必须有该 scope 的发布权限。

如果还没有该 scope：

1. 在 npm 创建名为 `omniaibot` 的组织，或改用你已有权限的 scope 并同步修改 `npm-packages/*/package.json` 中的包名
2. 确认发布账号是该组织的 owner/member，并具备 publish 权限
3. 如果使用 Granular Access Token，授权范围要覆盖 `@omniaibot/*`；首次发布新包时建议授权该 scope 下的所有包

## 2. 创建npm访问令牌

1. 登录 [npmjs.com](https://www.npmjs.com/)
2. 点击右上角头像 → "Access Tokens"
3. 点击 "Generate New Token"
4. 如果账号开启了 2FA，选择 "Automation" 类型，或创建带有 publish 权限且启用 "Bypass 2FA" 的 Granular Access Token
5. 复制生成的令牌

## 3. 配置GitHub Secrets

1. 进入GitHub仓库页面
2. 点击 "Settings" → "Secrets and variables" → "Actions"
3. 点击 "New repository secret"
4. 名称：`NPM_TOKEN`
5. 值：粘贴npm访问令牌
6. 点击 "Add secret"

## 4. 验证配置

推送版本标签后，观察GitHub Actions工作流：
- Build & Release Executables 工作流应成功完成
- Publish to npm 工作流应自动触发
- 检查npm注册表是否发布成功

## 5. 故障排除

### 工作流未触发
- 确认标签格式为 `v*`（如 `v1.0.0`）
- 确认构建工作流成功完成
- 检查 `NPM_TOKEN` 是否正确配置

### 发布失败
- 检查npm令牌权限
- 如果出现 `Two-factor authentication or granular access token with bypass 2fa enabled is required`，重新生成令牌：使用 Automation token，或使用启用 "Bypass 2FA" 的 Granular Access Token，然后更新 GitHub Secret `NPM_TOKEN`
- 如果出现 `Scope not found`，说明 `@omniaibot` scope 不存在，或 `NPM_TOKEN` 所属账号没有该 scope 的发布权限。先在 npm 创建 `omniaibot` 组织，或改用已有权限的 scope
- 确认包名未被占用
- 检查版本号是否已存在

## 6. 令牌安全

- 使用 "Automation" 类型令牌，或使用启用 "Bypass 2FA" 的 Granular Access Token，避免 CI 发布被双因素认证阻塞
- 定期轮换令牌（建议每6个月）
- 不要在代码中硬编码令牌
