if __name__ == '__main__':
    import os
    from pathlib import Path
    # The desktop dependency runtime needs Tcl scripts in the workspace sandbox.
    runtime = Path(__file__).resolve().parents[1] / 'build/runtime'
    if runtime.exists():
        os.environ.setdefault('TCL_LIBRARY', str(runtime/'tcl8.6'))
        os.environ.setdefault('TK_LIBRARY', str(runtime/'tk8.6'))
    import sys
    # MAA may spawn a persistent ADB server; it must not inherit the EXE folder.
    if getattr(sys, 'frozen', False):
        if '--self-test' in sys.argv or '--smoke-test' in sys.argv:
            flag='--self-test' if '--self-test' in sys.argv else '--smoke-test'
            index = sys.argv.index(flag) + 1
            sys.argv[index] = str(Path(sys.argv[index]).resolve())
        from fishing.paths import detach_working_directory
        detach_working_directory()
    if '--smoke-test' in sys.argv:
        from fishing.startup import main
        main(discover=False,hotkeys=False,smoke_path=sys.argv[sys.argv.index('--smoke-test')+1])
    elif '--self-test' in sys.argv:
        try:
            import pyi_splash
            pyi_splash.close()
        except ImportError:
            pass
        from fishing.selftest import selftest
        destination = sys.argv[sys.argv.index('--self-test')+1]
        try:
            selftest(destination, verify_maatouch='--verify-maatouch' in sys.argv)
        except Exception:
            import traceback
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            Path(destination).write_text(traceback.format_exc(), encoding='utf-8')
            sys.exit(1)
    else:
        from fishing.startup import main
        main()
