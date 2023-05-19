package org.crazybunqnq.svn2git.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
@ConfigurationProperties(prefix = "git")
@Data
public class UserEmailMapConfig {
    private Map<String, String> userMap;
}
