if __name__ == '__main__':
    import sys
    if getattr(sys, 'frozen', False):
        from autotata.paths import detach_working_directory
        detach_working_directory()
    from autotata.app import main
    main()
