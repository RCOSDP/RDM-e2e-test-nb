FROM tomcat:11-jdk17-temurin

ARG IDP_VERSION=5.2.3
RUN curl -fsSL "https://shibboleth.net/downloads/identity-provider/${IDP_VERSION}/shibboleth-identity-provider-${IDP_VERSION}.tar.gz" -o /tmp/idp.tar.gz \
    && mkdir /opt/idp-distribution \
    && tar -xzf /tmp/idp.tar.gz --strip-components=1 -C /opt/idp-distribution \
    && rm /tmp/idp.tar.gz
# This isolated HTTP fixture cannot use the distribution's __Host- secure cookie.
RUN sed -i -e 's/__Host-JSESSIONID/JSESSIONID_IDP/' \
    -e 's|<path>/</path>|<path>/idp</path>|' \
    -e 's|<secure>true</secure>|<secure>false</secure>|' \
    /opt/idp-distribution/webapp/WEB-INF/web.xml
COPY consent.css /opt/consent.css
COPY install.properties /opt/install.properties
RUN curl -fsSL https://repo.maven.apache.org/maven2/jakarta/servlet/jsp/jstl/jakarta.servlet.jsp.jstl-api/3.0.2/jakarta.servlet.jsp.jstl-api-3.0.2.jar -o /usr/local/tomcat/lib/jakarta.servlet.jsp.jstl-api.jar \
    && curl -fsSL https://repo.maven.apache.org/maven2/org/glassfish/web/jakarta.servlet.jsp.jstl/3.0.1/jakarta.servlet.jsp.jstl-3.0.1.jar -o /usr/local/tomcat/lib/jakarta.servlet.jsp.jstl.jar
COPY conf /opt/e2e-conf
COPY start.sh /usr/local/bin/start-idp
RUN mkdir -p /usr/local/tomcat/conf/Catalina/localhost \
    && echo '<Context docBase="/opt/shibboleth-idp/war/idp.war" privileged="true" swallowOutput="true" />' > /usr/local/tomcat/conf/Catalina/localhost/idp.xml
ENV CATALINA_OPTS="-Didp.home=/opt/shibboleth-idp -Xmx512m"
CMD ["bash", "/usr/local/bin/start-idp"]
