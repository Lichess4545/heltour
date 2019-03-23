module.exports = function(grunt) {
    require('time-grunt')(grunt);
    // Load prefixer config file
    var configBridge = grunt.file.readJSON('./assets/scss/config/configBridge.json', { encoding: 'utf8' });

    // 1. Project configuration
    grunt.initConfig({

    pkg: grunt.file.readJSON('package.json'),

        notify: {
            watch: {
                options: {
                    title: 'Task Complete',
                    message: 'sass Files Compiled'
                }
            },
            server: {
                options: {
                    message: 'Server is ready!'
                }
            },
            dist: {
                options: {
                    message: 'CSS files minified and distributed'
                }
            }
        },

        clean: {
          dist: ["dist/*"],
        },

        sass: {                         // Task
            dist: {                     // Target
                options: {              // Target options
                    sourceMap: true
                },
                files: {                                                 // Dictionary of files
                    'assets/css/style.css': 'assets/scss/style.scss',    // 'destination': 'source'
                }
            }
        },



        cssmin: {
            dist: {
                options: {
                    keepSpecialComments: '0'
                },
                files: {
                    'assets/css/style.min.css': ['assets/css/style.css']
                }
            }
        },

        connect: {
          server: {
            options: {
              port: 3000,
              base: 'dist',
              hostname: '127.0.0.1',
              livereload: true
            }
          }
        },

        watch: {
            livereload: {
                options: { livereload: true },
                files: ['assets/**/*', '*.html', 'partials/*.html'],
            },
            sass: {
                files: ['assets/scss/**/*.scss'],
                tasks: ['sass:dist', 'csscomb:dist', 'cssmin:dist', 'autoprefixer:styles', 'copy:dist', 'notify:dist'],
                options: {
                    spawn: false
                }
            }
        },

        csscomb: {
            dist: {
                options: {
                    config: 'assets/scss/config/csscomb.json'
                },
                expand: true,
                cwd: 'assets/scss/modules/',
                src: ['*.scss', '!_variables.scss'],
                dest: 'assets/scss/modules/',
                ext: '.scss'

            }
        },

        autoprefixer: {
            options: {
                browsers: configBridge.config.autoprefixerBrowsers
            },
            styles: {
                options: {
                    map: true
                },
                src: 'assets/css/style.css'
            }
        },

        copy: {
            dist: {
                files: [
                    /*STATIC*/
                    {expand: true, src: ['assets/css/*'], dest: 'dist/'},

                    /*Heltour*/
                    {expand: true, src: ['assets/css/*'], dest: '../heltour/tournament/static/tournament/'}
                ],
            },
        },

        open: {
            dev: {
                path: 'http://127.0.0.1:3000',
                app: 'Google Chrome'
            }
        }

    });

    // 3. Where we tell Grunt we plan to use this plug-in.
    grunt.loadNpmTasks('grunt-contrib-concat');
    //grunt.loadNpmTasks('grunt-contrib-jshint');
    //grunt.loadNpmTasks('grunt-contrib-uglify');
    grunt.loadNpmTasks('grunt-contrib-csslint');
    grunt.loadNpmTasks('grunt-contrib-cssmin');
    grunt.loadNpmTasks('grunt-contrib-copy');
    grunt.loadNpmTasks('grunt-contrib-connect');
    grunt.loadNpmTasks('grunt-contrib-watch');
    grunt.loadNpmTasks('grunt-contrib-copy');
    grunt.loadNpmTasks('grunt-notify');
    //grunt.loadNpmTasks('grunt-include-replace');
    grunt.loadNpmTasks('grunt-contrib-clean');
    grunt.loadNpmTasks('grunt-autoprefixer');
    grunt.loadNpmTasks('grunt-csscomb');
    grunt.loadNpmTasks('grunt-open');
    grunt.loadNpmTasks('grunt-sass');


    // 4. Where we tell Grunt what to do when we type "grunt" into the terminal.
    grunt.registerTask('default', ['clean:dist', 'sass:dist', 'csscomb:dist', 'autoprefixer:styles', 'cssmin:dist', 'copy:dist', 'notify:dist', 'watch']);
    grunt.registerTask('dist', ['sass:dist', 'csscomb:dist', 'autoprefixer:styles', 'cssmin:dist', 'notify:dist']);

};
