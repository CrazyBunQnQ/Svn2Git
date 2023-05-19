package org.crazybunqnq.svn2git.config;

import lombok.Data;
import org.crazybunqnq.svn2git.entity.SvnGitConfig;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
@ConfigurationProperties(prefix = "")
@Data
public class SvnGitProjectMapConfig {
    private Map<String, SvnGitConfig> svnGitMapping;
}
