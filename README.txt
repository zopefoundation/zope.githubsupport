This package provides a few simple scripts to administrate the Zope Foundation
GitHub repositories.


* Add GitHub Repository::

    $ addrepos --user <gh-username> --pass <gh-pwd> <name> "<description>"

* Migrate a Package from SVN to Git:

    $ migrate -c --user <gh-username> --pass <gh-pwd> <name> "<description>"

Note: For the scripts to properly run, you need to properly configure the
configuration file.
