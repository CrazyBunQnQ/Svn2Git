package org.crazybunqnq.svn2git.controller;

import org.crazybunqnq.svn2git.config.SvnGitProjectMapConfig;
import org.crazybunqnq.svn2git.entity.SvnGitConfig;
import org.crazybunqnq.svn2git.service.ISvnGitService;
import org.crazybunqnq.svn2git.service.impl.SvnGitServiceImpl;
import org.eclipse.jgit.util.StringUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import org.tmatesoft.svn.core.SVNException;

import java.io.IOException;
import java.util.Map;
import java.util.regex.Pattern;


@RestController
@RequestMapping("/sync")
public class SvnGitController {
    private static final Logger logger = LoggerFactory.getLogger(SvnGitController.class);

    @Autowired
    private SvnGitProjectMapConfig svnGitProjectMaping;

    @Autowired
    private ISvnGitService svnGitService;

    @GetMapping("/{repoName}")//TODO 手动调用后同步完成发邮件提醒
    public String send(@PathVariable(value = "repoName", required = false) String repoName, @RequestParam(value = "mail", required = false) String mail) {
        if (SvnGitServiceImpl.STATUS != 0) {
            return "仓库同步任务已在进行中, 请稍后再试";
        }

        try {
            Map<String, SvnGitConfig> svnGitConfigMap = this.svnGitProjectMaping.getSvnGitMapping();
            if (StringUtils.isEmptyOrNull(repoName) || "all".equals(repoName.toLowerCase())) {
                for (String key : svnGitConfigMap.keySet()) {
                    SvnGitConfig svnGitConfig = svnGitConfigMap.get(key);
                    svnGitService.syncSvnCommit2Git(svnGitConfig.getSvnUrl(), svnGitConfig.getSvnProjectPath(), svnGitConfig.getGitProjectPath(),
                            svnGitConfig.getDirRegx() != null ? Pattern.compile(svnGitConfig.getDirRegx()) : null, svnGitConfig.getDirSuffix());
                }
            } else {
                SvnGitConfig svnGitConfig = svnGitConfigMap.get(repoName);
                if (svnGitConfig == null) {
                    return "未找到仓库配置信息";
                }
                svnGitService.syncSvnCommit2Git(svnGitConfig.getSvnUrl(), svnGitConfig.getSvnProjectPath(), svnGitConfig.getGitProjectPath(),
                        svnGitConfig.getDirRegx() != null ? Pattern.compile(svnGitConfig.getDirRegx()) : null, svnGitConfig.getDirSuffix());
            }
        } catch (SVNException | IOException e) {
            e.printStackTrace();
            return "同步仓库失败: " + e.getMessage();
        }
        return "已调起同步仓库任务，请稍后查看 Git 远程仓库状态";
    }
}
