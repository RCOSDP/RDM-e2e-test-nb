"""Configure a disposable RDM checkout after setup_rdm.sh's base configuration."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[2] / 'docker/shibboleth'
HOST = 'http://192.168.168.167'
IDP = f'{HOST}:18089/idp/shibboleth'
SP = f'{HOST}:18088/shibboleth'
MD = 'urn:oasis:names:tc:SAML:2.0:metadata'
DS = 'http://www.w3.org/2000/09/xmldsig#'
SAML = 'urn:oasis:names:tc:SAML:2.0:protocol'
ET.register_namespace('md', MD)
ET.register_namespace('ds', DS)


def metadata(path, entity, role, certificate):
    root = ET.Element(f'{{{MD}}}EntityDescriptor', entityID=entity)
    descriptor = ET.SubElement(root, f'{{{MD}}}{role}', protocolSupportEnumeration=SAML)
    key = ET.SubElement(descriptor, f'{{{MD}}}KeyDescriptor')
    info = ET.SubElement(key, f'{{{DS}}}KeyInfo')
    data = ET.SubElement(info, f'{{{DS}}}X509Data')
    ET.SubElement(data, f'{{{DS}}}X509Certificate').text = ''.join(
        line for line in certificate.read_text().splitlines() if not line.startswith('-----'))
    if role == 'SPSSODescriptor':
        for index, port in enumerate((18088, 18087)):
            ET.SubElement(descriptor, f'{{{MD}}}AssertionConsumerService',
                          Binding=f'{SAML.rsplit(":", 1)[0]}:bindings:HTTP-POST',
                          Location=f'{HOST}:{port}/Shibboleth.sso/SAML2/POST', index=str(index))
    else:
        extensions = ET.Element(f'{{{MD}}}Extensions')
        ET.SubElement(extensions, '{urn:mace:shibboleth:metadata:1.0}Scope', regexp='false').text = 'e2e.test'
        descriptor.insert(0, extensions)
        ET.SubElement(descriptor, f'{{{MD}}}SingleSignOnService',
                      Binding='urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
                      Location=f'{HOST}:18089/idp/profile/SAML2/Redirect/SSO')
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def ds_config(port, target):
    return '\n'.join(f'var {key} = {json.dumps(value)};' for key, value in {
        'wayf_URL': 'https://ds.gakunin.nii.ac.jp/WAYF',
        'wayf_sp_entityID': SP,
        'wayf_sp_handlerURL': f'{HOST}:{port}/Shibboleth.sso',
        'wayf_sp_samlDSURL': f'{HOST}:{port}/Shibboleth.sso/Login',
        'wayf_return_url': target,
        'wayf_auto_login': False,
        'wayf_additional_idps': [{'name': 'RDM E2E Test IdP', 'entityID': IDP}],
    }.items()) + '\n'


def configure(rdm, cas_image):
    for directory, suffix in (('shields', ''), ('shields-rounded-corners', '-rounded-corners')):
        images = rdm / 'website/static/img/institutions' / directory
        shutil.copyfile(images / f'gakunin-shield{suffix}.png', images / f'e2esh-shield{suffix}.png')
    runtime = rdm / 'shibboleth'
    runtime.mkdir()
    exchange = runtime / 'exchange'
    exchange.mkdir()
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-nodes',
                    '-days', '2', '-subj', '/CN=RDM E2E SP',
                    '-keyout', str(exchange / 'sp-key.pem'),
                    '-out', str(exchange / 'sp-cert.pem')], check=True)
    # The upstream SP drops privileges to shibd, while this fixture is mounted read-only.
    (exchange / 'sp-key.pem').chmod(0o644)
    metadata(exchange / 'sp-metadata.xml', SP, 'SPSSODescriptor', exchange / 'sp-cert.pem')
    shutil.copytree(ROOT / 'sp', runtime / 'sp')
    (runtime / 'sp/discovery/config.js').write_text(ds_config(18088, ''))
    js = runtime / 'sp' / 'js'
    js.mkdir()
    (js / 'embedded-wayf_disp.js').write_text('')
    (js / 'embedded-wayf_config.js').write_text(ds_config(18087, f'{HOST}:18087/account/shib-login'))
    (runtime / 'dsconfig_js').write_text(ds_config(18088, f'{HOST}:18088/login?service={HOST}:5000/'))
    shutil.copytree(ROOT / 'cas', runtime / 'cas')
    properties = (rdm / 'etc/cas-overlay/cas.properties').read_text()
    updates = {
        'server.name': f'{HOST}:18088',
        'osf.url': f'{HOST}:5000/',
        'osf.api.institutions.auth.url': 'http://api:8000/v2/institutions/auth/',
        'osf.api.institutions.auth.xslLocation': 'file:/etc/cas/institutions-auth.xsl',
        'service.registry.config.location': 'file:/etc/cas/services',
        'log4j.config.location': 'file:/etc/cas/log4j2.xml',
    }
    for key, value in updates.items():
        properties, count = re.subn(r'^' + re.escape(key) + r'=.*$', key + '=' + value,
                                    properties, flags=re.MULTILINE)
        assert count == 1, (key, count)
    properties += '\nosf.api.institutions.login.availability.url=http://api:8000/v2/institutions/login_availability/\n'
    (runtime / 'cas/cas.properties').write_text(properties)
    for settings, content in {
        'website/settings/local.py': '\nUSE_EMBEDDED_DS = True\nLOGIN_BY_EPPN = True\n',
        'api/base/settings/local.py': "\nLOGIN_BY_EPPN = True\nALLOWED_HOSTS.append('api')\n",
        'admin/base/settings/local.py': (
            '\nENABLE_LOGIN_FORM = False\nENABLE_SHB_LOGIN = True\n'
            'EMBEDDED_DS_URL = "https://ds.gakunin.nii.ac.jp/WAYF/embedded-wayf.js"\n'),
    }.items():
        with (rdm / settings).open('a') as output:
            output.write(content)
    env = rdm / '.docker-compose.env'
    env.write_text(re.sub(r'^CAS_SERVER_URL=.*$', f'CAS_SERVER_URL={HOST}:18088',
                         env.read_text(), flags=re.MULTILINE))
    override = rdm / 'docker-compose.override.yml'
    compose = yaml.safe_load(override.read_text())
    services = compose['services']
    services['cas']['volumes'] = [
        f'{runtime}/cas/cas.properties:/etc/cas/cas.properties:ro',
        f'{runtime}/cas/institutions-auth.xsl:/etc/cas/institutions-auth.xsl:ro',
    ]
    services['cas']['image'] = cas_image
    services['ember_osf_web']['volumes'] = [f'{runtime}/dsconfig_js:/code/public/dsconfig_js:ro']
    services['ember_osf_web']['environment'].update({
        'NAV_EMBEDDEDDS_ENABLED': 'true', 'CAS_URL': f'{HOST}:18088',
    })
    services['idp'] = {
        'image': 'rdm-idp:shibboleth', 'ports': ['18089:8080'],
        'volumes': [f'{exchange}:/exchange'],
    }
    services['shibboleth_sp'] = {
        'image': 'rdm-sp:shibboleth', 'ports': ['18088:80', '18087:81'],
        'volumes': [f'{exchange}:/exchange:ro', f'{runtime}/sp:/etc/e2e:ro',
                    f'{runtime}/sp/httpd.conf:/etc/httpd/conf.d/e2e.conf:ro',
                    f'{runtime}/sp/shibboleth2.xml:/etc/shibboleth/shibboleth2.xml:ro',
                    f'{runtime}/sp/attribute-map.xml:/etc/shibboleth/attribute-map.xml:ro'],
    }
    override.write_text(yaml.safe_dump(compose, sort_keys=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['configure', 'idp-metadata'])
    parser.add_argument('rdm', type=Path)
    parser.add_argument('--cas-image', default='rdm-cas:shibboleth')
    args = parser.parse_args()
    rdm = args.rdm.resolve()
    if args.action == 'configure':
        configure(rdm, args.cas_image)
    else:
        exchange = rdm / 'shibboleth/exchange'
        metadata(exchange / 'idp-metadata.xml', IDP, 'IDPSSODescriptor', exchange / 'idp-signing.crt')
