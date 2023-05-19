package org.crazybunqnq.svn2git.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class SvnGitConfig {
    private String svnUrl;
    private String svnProjectPath;
    private String gitProjectPath;
    private String dirRegx;
}
