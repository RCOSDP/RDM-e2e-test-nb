#!/bin/bash
set -euo pipefail

# Generate signing and encryption keys for this disposable run, never in the image.
if [ ! -f /opt/shibboleth-idp/war/idp.war ]; then
    /opt/idp-distribution/bin/install.sh --noPrompt \
    --targetDir /opt/shibboleth-idp --hostName idp.e2e.test \
    --entityID http://192.168.168.167:18089/idp/shibboleth \
    --propertyFile /opt/install.properties \
    --keystorePassword ci-fixture-only --sealerPassword ci-fixture-only
    /opt/shibboleth-idp/bin/module.sh -e idp.authn.Password
    /opt/shibboleth-idp/bin/module.sh -e idp.intercept.Consent
    cat /opt/consent.css >> /opt/shibboleth-idp/edit-webapp/css/placeholder.css
    /opt/shibboleth-idp/bin/build.sh --noPrompt
fi
cp -R /opt/e2e-conf/. /opt/shibboleth-idp/conf/
cat >> /opt/shibboleth-idp/conf/idp.properties <<'EOF'
idp.cookie.secure = false
idp.session.cookieName = shib_idp_session
idp.session.StorageService = shibboleth.StorageService
EOF
for user in testuser1 testuser2 teststaff; do
    printf '%s:%s\n' "$user" "$(openssl passwd -6 ci-fixture-password)"
done > /opt/shibboleth-idp/conf/authn/htpasswd.txt
cp /opt/shibboleth-idp/credentials/idp-signing.crt /exchange/idp-signing.crt
chmod 644 /exchange/idp-signing.crt
exec catalina.sh run
