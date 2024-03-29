package org.crazybunqnq.svn2git.schedule;

import org.crazybunqnq.svn2git.config.SvnGitProjectMapConfig;
import org.crazybunqnq.svn2git.entity.SvnGitConfig;
import org.crazybunqnq.svn2git.service.ISvnGitService;
import org.crazybunqnq.svn2git.service.impl.SvnGitServiceImpl;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.tmatesoft.svn.core.SVNException;

import java.io.IOException;
import java.util.Map;
import java.util.regex.Pattern;


@Component
public class SyncSvn2Git {
    private static final Logger logger = LoggerFactory.getLogger(SyncSvn2Git.class);

    @Autowired
    private ISvnGitService svnGitService;

    @Autowired
    private SvnGitProjectMapConfig svnGitProjectMaping;

    @Scheduled(cron = "0 0/3 * * * ?")
    public void changeTime() {
        if (SvnGitServiceImpl.STATUS != 0) {
            logger.info("同步任务进行中，本次定时同步跳过");
            return;
        }
        logger.info("定时同步 SVN 到 Git");
        // svnGitService.test();

        try {
            Map<String, SvnGitConfig> svnGitConfigMap = svnGitProjectMaping.getSvnGitMapping();
            for (String key : svnGitConfigMap.keySet()) {
                SvnGitConfig svnGitConfig = svnGitConfigMap.get(key);
                svnGitService.syncSvnCommit2Git(svnGitConfig.getSvnUrl(), svnGitConfig.getSvnProjectPath(), svnGitConfig.getGitProjectPath(),
                        svnGitConfig.getDirRegx() == null ? null : Pattern.compile(svnGitConfig.getDirRegx()), svnGitConfig.getDirSuffix());
            }
        } catch (SVNException | IOException e) {
            logger.info("同步仓库失败: " + e.getMessage());
            e.printStackTrace();
        }
    }
}
