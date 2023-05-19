package org.crazybunqnq.svn2git.controller;

import org.crazybunqnq.svn2git.entity.SvnGitConfig;
import org.crazybunqnq.svn2git.service.ISvnGitService;
import org.crazybunqnq.svn2git.service.impl.SvnGitServiceImpl;
import org.eclipse.jgit.util.StringUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.tmatesoft.svn.core.SVNException;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import java.util.regex.Pattern;


@RestController
@RequestMapping("/sync")
public class SvnGitController {
    private static final Logger logger = LoggerFactory.getLogger(SvnGitController.class);
    private static Map<String, SvnGitConfig> svnGitConfigMap = new HashMap<>(2);

    // TODO 通过配置读取
    static {
        svnGitConfigMap.put("Singularity",
                new SvnGitConfig("https://192.168.0.182:8443/repo/codes/SafeMg/Singularity",
                        "F:\\SvnRepo\\Singularity",
                        "F:\\GitRepo\\Singularity",
                        ".*/Singularity/([^/]+).*"));
        svnGitConfigMap.put("Platform",
                new SvnGitConfig("https://192.168.0.182:8443/repo/codes/SafeMg/SMPlatform/branches",
                        "F:\\SvnRepo\\SMPlatform",
                        "F:\\GitRepo\\Platform",
                        ".*/branches/([^/]+).*"));
    }

    @Autowired
    private ISvnGitService svnGitService;

    @GetMapping("/{repoName}")
    public String send(@PathVariable("repoName") String repoName) {
        if (SvnGitServiceImpl.STATUS != 0) {
            return "仓库同步任务已在进行中, 请稍后再试";
        }

        try {
            if (StringUtils.isEmptyOrNull(repoName)) {
                for (String key : svnGitConfigMap.keySet()) {
                    SvnGitConfig svnGitConfig = svnGitConfigMap.get(key);
                    svnGitService.syncSvnCommit2Git(svnGitConfig.getSvnUrl(), svnGitConfig.getSvnProjectPath(), svnGitConfig.getGitProjectPath(), Pattern.compile(svnGitConfig.getDirRegx()));
                }
            } else {
                SvnGitConfig svnGitConfig = svnGitConfigMap.get(repoName);
                if (svnGitConfig == null) {
                    return "未找到仓库配置信息";
                }
                svnGitService.syncSvnCommit2Git(svnGitConfig.getSvnUrl(), svnGitConfig.getSvnProjectPath(), svnGitConfig.getGitProjectPath(), Pattern.compile(svnGitConfig.getDirRegx()));
            }
        } catch (SVNException | IOException e) {
            e.printStackTrace();
            return "同步仓库失败: " + e.getMessage();
        }
        return "已调起同步仓库任务，请稍后查看 Git 远程仓库状态";
    }
}
