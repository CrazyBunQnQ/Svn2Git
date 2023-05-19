package org.crazybunqnq.svn2git.service;

import org.tmatesoft.svn.core.SVNException;

import java.io.IOException;
import java.util.regex.Pattern;

public interface ISvnGitService {
    void test();
    void syncSvnCommit2Git(String svnUrl, String svnRepoPath, String gitRepoPath, Pattern dirRegx) throws SVNException, IOException;
}
