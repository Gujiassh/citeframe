# Controller geometry verification

Controller independently executed frozen product62B89093C67B88B16CB926C61A4DC1FC3725341332350B32BD88FFCA4532368C and test538AB2C3575E04EDC66BBC2DBC43A573DE05BCB9B07B3598CCADB902FA3B25F2 using existing API Python3.12 on Windows, not the developer-root executor.

First command: python -B -m pytest --noconftest --strict-markers -p no:cacheprovider -o pythonpath= -o xfail_strict=true -q apps/api/tests/test_native_image_geometry.py. Result119passed1.45s, zero skips.

Then executed the exact inline body from workflow82600A9CCA24A89F1FBC70460E9F0F9CBE23A4E1D370FD9AE86B01F16F4C5D26, dedented without semantic changes, with PYTHONDONTWRITEBYTECODE=1, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 and no PYTHONPATH. Its actual import/network/result guards ran:119passed2.88s, exit0. This is local Windows evidence, not frozen install or Linux parity.

Existing actionlint1.7.12 with -no-color -shellcheck= -pyflakes= on this workflow returned0 without diagnostics. Shellcheck/pyflakes not executed. Product/test hashes retained. Original independent product review is FFBEDACA; original targeted CI review pending. No native activation, launcher/build change, paid model or previously denied UI operation.
