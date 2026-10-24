<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:template match="/">
        <xsl:if test="auth/attribute[@name='Delegation-Protocol']/@value != 'saml-shib' or auth/attribute[@name='Shib-Identity-Provider']/@value != 'http://192.168.168.167:18089/idp/shibboleth'">
            <xsl:message terminate="yes">Unexpected authentication provider</xsl:message>
        </xsl:if>
        <provider>
            <id>e2esh</id>
            <idp><xsl:value-of select="auth/attribute[@name='Shib-Identity-Provider']/@value" /></idp>
            <user>
                <username><xsl:value-of select="auth/attribute[@name='eppn']/@value" /></username>
                <fullname><xsl:value-of select="auth/attribute[@name='displayName']/@value" /></fullname>
                <givenName><xsl:value-of select="auth/attribute[@name='givenName']/@value" /></givenName>
                <familyName><xsl:value-of select="auth/attribute[@name='sn']/@value" /></familyName>
                <email><xsl:value-of select="auth/attribute[@name='mail']/@value" /></email>
                <entitlement><xsl:value-of select="auth/attribute[@name='entitlement']/@value" /></entitlement>
                <organizationName><xsl:value-of select="auth/attribute[@name='o']/@value" /></organizationName>
            </user>
        </provider>
    </xsl:template>
</xsl:stylesheet>
