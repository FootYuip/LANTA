# CODESYS 工程导出区

把从 CODESYS 导出的文件放进本文件夹即可。在对话里说「分析 codesys-export」或「分析当前 PLC 工程」，助手会读取这里的文件，解析配置与 ST 代码。

## 推荐放入的文件

| 文件类型 | 在 CODESYS 中的操作 | 用途 |
|----------|---------------------|------|
| **`.xml`**（首选） | **文件 → 导出 → PLCopen XML…** | 程序、GVL、DUT、任务绑定等，最适合代码与逻辑分析 |
| **`.export`**（可选） | **文件 → 导出 → 导出工程…** | 完整工程归档（设备树、可视化、库引用等），体积较大 |
| **`.project`**（可选） | 直接复制工程目录中的 `.project` | 辅助对照工程名与版本，分析仍以 `.xml` 为主 |

说明：

- 文件夹里可以只有 **一个** `.xml`；若有多个，转换脚本会选用**体积最大**的那个（视为主导出）。
- 导出后**不必改名**，保留 CODESYS 默认文件名即可。
- 每次改完工程逻辑，重新导出并**覆盖或新增**本目录中的文件，再让我分析，结果才与现场一致。

## 导出步骤（PLCopen XML）

1. 在 CODESYS 中打开你的工程（例如 `1m8QV… .project`）。
2. 菜单：**文件 → 导出 → PLCopen XML…**
3. 保存路径选本仓库下的 **`codesys-export`** 文件夹。
4. 在 Cursor 对话中说明要分析的内容（例如：Modbus 映射、轴控制、任务周期）。

## 助手如何处理这些文件

1. 读取 `codesys-export` 中的 `.xml`（以及需要时的 `.export`）。
2. 运行仓库脚本，将 XML 转为便于阅读的文本树：

   ```bash
   python scripts/export_plcopen_to_txt.py
   ```

   默认：输入 `codesys-export/`，输出 `plc-src/`。

3. 结合 `plc-src` 下的 `.txt` 与 `plc-src/LEARNING_PATH.md` 做配置、变量地址、POU 逻辑等方面的说明。

## 目录分工

| 目录 | 角色 |
|------|------|
| **`codesys-export/`** | 你只负责：把 CODESYS 导出文件放进来 |
| **`plc-src/`** | 由脚本自动生成，供阅读与分析（勿当作在 CODESYS 里改动的源） |
| **`scripts/export_plcopen_to_txt.py`** | XML → txt 转换工具 |

## 从旧目录迁移

若你之前在 `project-rebuid/` 里放过导出文件，可整体移到 `codesys-export/`，之后只往这里放新导出即可。
