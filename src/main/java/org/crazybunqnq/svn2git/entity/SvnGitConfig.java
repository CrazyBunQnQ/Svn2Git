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
    /**
     * 取分支的正则表达式
     */
    private String dirRegx;
    /**
     * 目录后缀
     */
    private String dirSuffix;
}
