> **Archived project notice (2026-08-28)**
>
> This personal AstrBot plugin source is retired and is no longer used. Reference snapshots are preserved in [memoriass/astrbot-plugins-archive](https://github.com/memoriass/astrbot-plugins-archive). Do not add this source to AstrBot installations.
# memoriass AstrBot 插件源

[![自动更新插件源](https://github.com/memoriass/astrbot-plugin-source/actions/workflows/update-registry.yml/badge.svg)](https://github.com/memoriass/astrbot-plugin-source/actions/workflows/update-registry.yml)

这是一个个人维护的 AstrBot 插件源，主要收录 `memoriass` 的公开插件，也接受其他开发者提交插件仓库。

## 使用

在 AstrBot WebUI 的插件市场里添加这个地址：

```text
https://raw.githubusercontent.com/memoriass/astrbot-plugin-source/main/plugins.json
```

MD5 地址：

```text
https://raw.githubusercontent.com/memoriass/astrbot-plugin-source/main/plugins-md5.json
```

## 提交插件

想把插件加进来，只需要改 `repositories.json`，添加你的公开仓库：

```json
{
  "owner": "your-github-name",
  "name": "your-astrbot-plugin-repo"
}
```

然后提交 Pull Request 即可。

插件仓库根目录需要有 AstrBot 可识别的 `metadata.yaml`，否则不会被生成进插件源。

## 更新规则

插件自己的版本、描述、logo、README 等内容变更时，只需要更新插件仓库。

只有新增、移除、修改插件仓库地址时，才需要改这个项目里的 `repositories.json`。

## 自动更新

GitHub Actions 会每 6 小时自动重新生成 `plugins.json` 和 `plugins-md5.json`。

如果刚合并了新插件，也可以手动运行：

```text
Actions -> Update AstrBot Plugin Registry -> Run workflow
```

## 本地生成

```powershell
python scripts/build_registry.py
```
