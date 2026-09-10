# 自动校相候选修改包

完整操作见 [添加与调试说明](添加与调试说明.md)。

- `apply_in_codesys.py`：在 CODESYS 内执行的离线候选生成脚本。
- `payload.json` / `payload.sha256`：源码基线、六对象更新及校验摘要。
- `generated/`：四个新增、两个修改对象的完整声明/实现，可手工粘贴。
- `GVL_PhaseCal.st`、`PRG_PhaseCalibration.st`、两个 `FB_*.st`：新增 ST 源码。
- `READ_485.append.st`：只供生成器使用的接收诊断片段。
- `build_package.py`：从现有镜像生成候选包，不覆盖镜像。
- `check_reference.py` / `test_package.py`：独立参考数学和打包/脚本保护测试，不执行 ST。

限制：仅支持远控双轴位置模式；默认接收对齐确认关闭，不能立即运动；未知硬件相移方向只给两个候选。详见操作说明。

原工程、原镜像和原导出均未改写。尚未经过 CODESYS 编译、完整镜像往返验证或实机测试，不能当作已验证上线版本。
