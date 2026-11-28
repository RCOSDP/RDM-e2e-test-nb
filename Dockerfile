FROM niicloudoperation/notebook@sha256:98c8ed6401038949998fd2d88e68a2ccdc82fe849aa61397d48fedc0bf31dee4

USER root

# Playwright
RUN pip --no-cache-dir install pytest-playwright && \
    playwright install

# AWSCLI
RUN mamba install --quiet --yes awscli passlib && mamba clean --all -f -y

RUN apt-get update && \
    apt-get -y install language-pack-ja firefox ffmpeg fonts-noto-cjk && \
    dpkg-reconfigure locales && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir openpyxl "Pillow>=9.2" "zxing-cpp>=3.0"
RUN rm -fr $HOME/*
ENV LANGUAGE=ja_JP.UTF-8 LANG=ja_JP.UTF-8


USER $NB_USER

COPY --chown=$NB_UID:$NB_GID . $HOME/

# Installing CS-jupyterlab-grdm https://github.com/RCOSDP/CS-jupyterlab-grdm/
#ENV grdm_jlab_release_tag=0.1.0 \
#    grdm_jlab_release_url=https://github.com/RCOSDP/CS-jupyterlab-grdm/releases/download/0.1.0
#RUN pip3 install ${grdm_jlab_release_url}/rdm_binderhub_jlabextension-refs.tags.${grdm_jlab_release_tag}.tar.gz \
#    && jupyter server extension enable rdm_binderhub_jlabextension \
#    && jupyter nbextension install --py rdm_binderhub_jlabextension --user \
#    && jupyter nbextension enable --py rdm_binderhub_jlabextension --user \
#    && jlpm cache clean \
#    && npm cache clean --force \
#    && pip3 cache purge
