project('imageflow',
          version: '0.9.6',
    meson_version: '>= 1.0.0',
  default_options: [ 'warning_level=2', 'werror=false', ],
)

i18n = import('i18n')
gnome = import('gnome')


subdir('data')
subdir('src')
subdir('po')

run_command('./update_l10n.sh', check: true)

gnome.post_install(
     glib_compile_schemas: true,
    gtk_update_icon_cache: true,
  update_desktop_database: true,
)
