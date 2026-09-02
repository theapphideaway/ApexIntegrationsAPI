"""Run Django's system check locally with stub env vars so URL/import errors
are caught BEFORE deploying (py_compile can't catch NameErrors in urls.py).
Usage: python3 scripts/localcheck.py"""
import os, re, glob, subprocess, sys
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(root, 'ApexIntegrationsAPI/settings.py')).read() + ''.join(open(f).read() for f in glob.glob(os.path.join(root, 'AccountsAdmin/*.py')))
names = set(re.findall(r"os\.environ(?:\.get)?[\(\[]['\"]([A-Z_0-9]+)['\"]", src))
env = dict(os.environ)
for n in names:
    env.setdefault(n, '1234567')
env.update(DATABASE_URL='', DJANGO_SECRET_KEY='localcheck', PUSHER_APP_ID='123456', PUSHER_CLUSTER='us2', MLS_LISTING_ID_FIELD='ListingId', OTP_DEV_BYPASS='')
sys.exit(subprocess.run([sys.executable, 'manage.py', 'check'], cwd=root, env=env).returncode)
