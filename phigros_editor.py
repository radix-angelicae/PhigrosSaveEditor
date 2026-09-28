# -*- coding: utf-8 -*-
"""
Phigros 云存档编辑器  (Phigros Cloud Save Editor)
------------------------------------------------------------------
功能：
  1. 打开本地存档压缩包，或从云端下载
  2. 解密并解析为结构化数据，用表格 / 表单可视化编辑，无需手写 JSON
  3. 撤销重做、搜索筛选、批量修改、B19/RKS 计算、浅色/深色主题
  4. 保存时重新序列化 + AES-256-CBC 加密 + 打包成与原版结构一致的 zip
  5. 云存档：拉取与上传（上传前自动备份）
  6. 命令行 --selftest 做「解析→重建」逐字节自检（不需要 tkinter）

运行：python phigros_editor.py
依赖：pip install pycryptodome        （tkinter 为 Python 内置）
"""

import sys


def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        print("用法：python phigros_editor.py [--selftest <存档.zip>]")
        return

    # 自检路径：只导入核心格式模块，完全不触碰 tkinter
    if len(args) >= 2 and args[0] == "--selftest":
        from phi_format import selftest
        sys.exit(0 if selftest(args[1]) else 1)
    if len(args) >= 2 and args[0] == "--selftest":
        print("用法：python phigros_editor.py --selftest <存档.zip>")
        sys.exit(2)

    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("当前环境没有 tkinter，无法启动界面。Windows 自带 Python 均包含 tkinter。")
        sys.exit(1)

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # Windows 高分屏适配
    except Exception:
        pass

    from phi_app import App
    try:
        App().mainloop()
    except Exception as e:
        print("启动失败：", e)
        raise


if __name__ == "__main__":
    main()
