package org.crazybunqnq.svn2git;

import org.crazybunqnq.entity.MergedSVNLogEntry;
import org.eclipse.jgit.api.Git;
import org.eclipse.jgit.api.Status;
import org.eclipse.jgit.api.errors.GitAPIException;
import org.eclipse.jgit.api.errors.RefNotFoundException;
import org.eclipse.jgit.lib.StoredConfig;
import org.junit.Test;
import org.tmatesoft.svn.core.*;
import org.tmatesoft.svn.core.auth.ISVNAuthenticationManager;
import org.tmatesoft.svn.core.io.SVNRepository;
import org.tmatesoft.svn.core.io.SVNRepositoryFactory;
import org.tmatesoft.svn.core.wc.*;

import java.io.*;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class Svn2GitTest {

    private final String SVN_URL = "https://192.168.0.182:8443/repo/codes/SafeMg/SMPlatform/branches";
    private final String USERNAME = "junjie";
    private final String PASSWORD = "junjie@20230301";
    private final String LOG_FILE_PATH = "svn_commit.log";

    private static Map<String, String> emailMap = new HashMap<>();

    private static final List<String> DELETE_WITELIST = Arrays.asList(new String[]{".git", ".idea", ".gitignore", ".svn_version", "svn_commit.log"});
    private static final List<String> BRANCH_WITELIST = Arrays.asList(new String[]{"platform-divider"});


    static {
        emailMap.put("baozi", "baozi@qq.com");
    }

    @Test
    public void getSvnCommitLogTest() throws SVNException, IOException {
        // 1. 获取 svn 仓库
        SVNRepository repository = setupSvnRepository(SVN_URL, USERNAME, PASSWORD);
        // 2. 获取 svn 仓库的提交记录
        List<SVNLogEntry> svnLogEntries = getSvnLogEntries(repository);
        // 3. 合并连续的提交记录
        List<MergedSVNLogEntry> mergedLogEntries = mergeConsecutiveCommits(svnLogEntries);
        // 4. 将合并后的提交记录写入文件
        writeSvnLogEntriesToFile(mergedLogEntries, LOG_FILE_PATH);
        long revision = readRevisionFromLogFile(LOG_FILE_PATH, null);
        while (revision > 0) {
            Long curSvnVersionInGit = getCurrentSvnVersionFromGit("F:\\GitRepo\\Platform");
            revision = readRevisionFromLogFile(LOG_FILE_PATH, curSvnVersionInGit);
            String author = readAuthorFromLogFile(LOG_FILE_PATH, revision);
            String commitMsg = readMessageFromLogFile(LOG_FILE_PATH, revision);
            System.out.println("开始更新 svn 版本到 " + revision);
            try {
                updateSvnToRevision("F:\\SvnRepo\\Platform", revision);
            } catch (Exception e) {
                e.printStackTrace();
                System.exit(1);
            }
            System.out.println("更新完成");
            Pattern branchRegx = Pattern.compile(".*/branches/([^/]+).*");
            System.out.println("开始读取提交记录");
            Map<String, List<SVNLogEntryPath>> changesByBranch = readChangesByBranchFromLogFile(LOG_FILE_PATH, revision, branchRegx);
            System.out.println("读取完成, 涉及 " + changesByBranch.size() + " 个分支");
            try {
                copySvnChangesToGit("F:\\SvnRepo\\Platform", "F:\\GitRepo\\Platform", changesByBranch, revision, author, commitMsg);
            } catch (Exception e) {
                e.printStackTrace();
                System.exit(1);
            }
        }
    }

    /**
     * 获取SVN仓库
     *
     * @param url
     * @param username
     * @param password
     * @return
     * @throws SVNException
     */
    private SVNRepository setupSvnRepository(String url, String username, String password) throws SVNException {
        SVNRepository repository = SVNRepositoryFactory.create(SVNURL.parseURIEncoded(url));
        ISVNAuthenticationManager authManager = SVNWCUtil.createDefaultAuthenticationManager(username, password.toCharArray());
        repository.setAuthenticationManager(authManager);
        return repository;
    }

    /**
     * 获取 svn 提交记录
     *
     * @param repository
     * @return
     * @throws SVNException
     */
    private List<SVNLogEntry> getSvnLogEntries(SVNRepository repository) throws SVNException {
        List<SVNLogEntry> logEntries = new ArrayList<>();
        repository.log(new String[]{""}, logEntries, 0, -1, true, true);
        return logEntries;
    }

    /**
     * 合并连续的提交记录
     *
     * @param logEntries
     * @return
     */
    private List<MergedSVNLogEntry> mergeConsecutiveCommits(List<SVNLogEntry> logEntries) {
        List<MergedSVNLogEntry> mergedLogEntries = new ArrayList<>();
        MergedSVNLogEntry previousEntry = null;

        for (SVNLogEntry logEntry : logEntries) {
            if (previousEntry == null || !previousEntry.getAuthor().equals(logEntry.getAuthor())) {
                previousEntry = new MergedSVNLogEntry(logEntry);
                mergedLogEntries.add(previousEntry);
            } else {
                previousEntry.setRevision(logEntry.getRevision());
                previousEntry.setDate(logEntry.getDate());
                previousEntry.setMessage(previousEntry.getMessage() + "\n" + logEntry.getMessage());

                for (Map.Entry<String, SVNLogEntryPath> entry : logEntry.getChangedPaths().entrySet()) {
                    previousEntry.getChangedPaths().put(entry.getKey(), entry.getValue());
                }
            }
        }
        return mergedLogEntries;
    }

    /**
     * 将 svn 提交记录写入文件
     *
     * @param logEntries
     * @param filePath
     * @throws IOException
     */
    private void writeSvnLogEntriesToFile(List<MergedSVNLogEntry> logEntries, String filePath) throws IOException {
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(filePath))) {
            for (MergedSVNLogEntry logEntry : logEntries) {
                writer.write("Revision: " + logEntry.getRevision() + "\n");
                writer.write("Author: " + logEntry.getAuthor() + "\n");
                writer.write("Date: " + logEntry.getDate() + "\n");
                writer.write("Message: " + logEntry.getMessage() + "\n");

                writer.write("Changed Paths:\n");
                for (Map.Entry<String, SVNLogEntryPath> entry : logEntry.getChangedPaths().entrySet()) {
                    writer.write(entry.getValue().getType() + " " + entry.getKey() + "\n");
                }
                writer.write("\n");
            }
        }
    }

    private void getDiffBy2VersionFromSvn(SVNRepository repository, Long preVersion, Long newVersion) throws SVNException, FileNotFoundException {
        // 配置日志参数
        // SVNLogClient logClient = new SVNLogClient(repository.getAuthenticationManager(), repository.createRepositoryPool());
        // ISVNAuthenticationManager authenticationManager = repository.getAuthenticationManager();
        // SVNLogClient logClient = new SVNLogClient(authenticationManager, repository.op
        SVNClientManager clientManager = SVNClientManager.newInstance();
        SVNLogClient logClient = clientManager.getLogClient();
        // logClient.setDiffOptions();

        ISVNLogEntryHandler logEntryHandler = logEntry -> {
            try (PrintWriter writer = new PrintWriter(new FileOutputStream(".svn_update", true))) {
                writer.println("Revision: " + logEntry.getRevision());
                writer.println("Author: " + logEntry.getAuthor());
                writer.println("Date: " + logEntry.getDate());
                writer.println("Message: " + logEntry.getMessage());

                for (Object path : logEntry.getChangedPaths().values()) {
                    SVNLogEntryPath entryPath = (SVNLogEntryPath) path;
                    writer.println("  " + entryPath.getType() + " " + entryPath.getPath());
                }
                writer.println();
            } catch (FileNotFoundException e) {
                throw new RuntimeException(e);
            }
        };

        // 获取日志并输出到文件
        SVNURL url = repository.getLocation();
        String[] targetPaths = new String[]{""};
        boolean stopOnCopy = false;
        boolean discoverChangedPaths = true;
        boolean includeMergedRevisions = false;
        long limit = 0L;

        logClient.doLog(url, targetPaths, null, SVNRevision.create(preVersion + 1), SVNRevision.create(newVersion),
                stopOnCopy, discoverChangedPaths, includeMergedRevisions, limit, null, logEntryHandler);
    }

    /**
     * 从文件中读取 revision
     *
     * @param gitRepoPath
     * @return
     * @throws IOException
     */
    private long getCurrentSvnVersionFromGit(String gitRepoPath) throws IOException {
        Path svnVersionFilePath = Paths.get(gitRepoPath, ".svn_version");
        if (Files.exists(svnVersionFilePath)) {
            String versionStr = new String(Files.readAllBytes(svnVersionFilePath));
            return Long.parseLong(versionStr.trim());
        }
        // 返回一个负数，表示没有找到版本文件，可以根据需要调整此值
        return -1L;
    }

    /**
     * 从文件中读取 revision
     *
     * @param filePath
     * @return
     * @throws IOException
     */
    private long readRevisionFromLogFile(String filePath, Long curVersion) throws IOException {
        try (BufferedReader reader = new BufferedReader(new FileReader(filePath))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.startsWith("Revision:")) {
                    Long reversion = Long.valueOf(line.split(" ")[1]);
                    if (curVersion != null && reversion <= curVersion) {
                        continue;
                    }
                    return reversion;
                }
            }
        }
        return -1;
    }

    /**
     * 从文件中读取 author
     *
     * @param filePath
     * @param version
     * @return
     * @throws IOException
     */
    private String readAuthorFromLogFile(String filePath, long version) throws IOException {
        try (BufferedReader reader = new BufferedReader(new FileReader(filePath))) {
            String line;
            boolean targetRevisionFound = false;
            while ((line = reader.readLine()) != null) {
                if (line.startsWith("Revision:") && Long.parseLong(line.split(" ")[1]) == version) {
                    targetRevisionFound = true;
                } else if (targetRevisionFound && line.startsWith("Author: ")) {
                    return line.split(" ")[1];
                }
            }
        }
        return null;
    }

    private String readMessageFromLogFile(String filePath, long version) throws IOException {
        try (BufferedReader reader = new BufferedReader(new FileReader(filePath))) {
            String line;
            boolean targetRevisionFound = false;
            while ((line = reader.readLine()) != null) {
                if (line.startsWith("Revision:") && Long.parseLong(line.split(" ")[1]) == version) {
                    targetRevisionFound = true;
                } else if (targetRevisionFound && line.startsWith("Message: ")) {
                    StringBuilder sb = new StringBuilder(line.substring(8));
                    while ((line = reader.readLine()) != null && !line.startsWith("Changed Paths:")) {
                        if (line.isEmpty()) {
                            continue;
                        }
                        sb.append(line);
                    }
                    return sb.toString().trim();
                }
            }
        }
        return null;
    }

    /**
     * 更新 SVN 项目到指定版本
     *
     * @param workingCopyPath
     * @param revision
     * @throws SVNException
     */
    private void updateSvnToRevision(String workingCopyPath, long revision) throws SVNException {
        SVNClientManager clientManager = SVNClientManager.newInstance();
        SVNUpdateClient updateClient = clientManager.getUpdateClient();
        updateClient.setIgnoreExternals(false);
        updateClient.doUpdate(Paths.get(workingCopyPath).toFile(), SVNRevision.create(revision), SVNDepth.INFINITY, true, true);
    }

    /**
     * 从日志文件中读取指定版本的变更
     *
     * @param filePath
     * @param revision
     * @param branchRegx
     * @return
     * @throws IOException
     */
    private Map<String, List<SVNLogEntryPath>> readChangesByBranchFromLogFile(String filePath, long revision, Pattern branchRegx) throws IOException {
        Map<String, List<SVNLogEntryPath>> changesByBranch = new HashMap<>();

        try (BufferedReader reader = new BufferedReader(new FileReader(filePath))) {
            String line;
            boolean targetRevisionFound = false;
            while ((line = reader.readLine()) != null) {
                if (line.startsWith("Revision:") && Long.parseLong(line.split(" ")[1]) == revision) {
                    targetRevisionFound = true;
                } else if (targetRevisionFound && line.startsWith("Changed Paths:")) {
                    while ((line = reader.readLine()) != null && !line.isEmpty()) {
                        // SVNLogEntryPath entryPath = new SVNLogEntryPath(line.substring(2), line.charAt(0), null, null);
                        SVNLogEntryPath entryPath = new SVNLogEntryPath(line.substring(2), line.charAt(0), null, revision);
                        String branch = getBranchFromPath(entryPath.getPath(), branchRegx);
                        changesByBranch.computeIfAbsent(branch, k -> new ArrayList<>()).add(entryPath);
                    }
                    break;
                }
            }
        }
        return changesByBranch;
    }

    /**
     * 从路径中获取分支名
     *
     * @param path
     * @return
     */
    private String getBranchFromPath(String path, Pattern pattern) {
        Matcher matcher = pattern.matcher(path);
        return matcher.find() ? matcher.group(1) : "master";
    }

    /**
     * 复制 SVN 的变更提交到 Git
     *
     * @param svnRepoPath
     * @param gitRepoPath
     * @param changesByBranch
     * @param version
     * @param author
     * @throws IOException
     * @throws GitAPIException
     */
    private static void copySvnChangesToGit(String svnRepoPath, String gitRepoPath, Map<String, List<SVNLogEntryPath>> changesByBranch, long version, String author, String commitMsg) throws IOException, GitAPIException {
        Git git = Git.open(new File(gitRepoPath));
        // 设置提交用户
        StoredConfig config = git.getRepository().getConfig();
        config.setString("user", null, "name", author);
        config.setString("user", null, "email", emailMap.get(author));
        // 将 changesByBranch 的 key 尾号进行排序
        List<String> sortedBranches = changesByBranch.keySet().stream().sorted().collect(Collectors.toList());

        for (String branch : sortedBranches) {
            String gitRepoName = gitRepoPath.substring(gitRepoPath.lastIndexOf(File.separator) + 1);
            if ("master".equals(branch) || (!branch.toLowerCase().startsWith(gitRepoName.toLowerCase() + "_") && !BRANCH_WITELIST.contains(branch))) {
                continue;
            }
            System.out.println("检出分支：" + branch);
            boolean isNewBranch = checkoutOrCreateBranch(git, branch);

            List<SVNLogEntryPath> svnLogEntryPaths = changesByBranch.get(branch);
            for (SVNLogEntryPath change : svnLogEntryPaths) {
                // 从 change.getPaht() 中截取 branch 之后的部分
                String path = change.getPath();
                String branchPath = path.substring(path.indexOf(branch));
                // 跳过分支根目录
                if (branchPath.length() == branch.length()) {
                    continue;
                }
                String contentPath = branchPath.substring(branchPath.indexOf(branch) + branch.length() + 1);
                Path targetPath = Paths.get(gitRepoPath, contentPath);
                File targetFile = targetPath.toFile();
                if (change.getType() == SVNLogEntryPath.TYPE_ADDED || change.getType() == SVNLogEntryPath.TYPE_MODIFIED) {
                    Path sourcePath = Paths.get(svnRepoPath, branchPath);
                    File sourceFile = sourcePath.toFile();
                    if (!sourceFile.exists()) {
                        System.out.println("Source file not exist or source file is directory: " + sourceFile.getAbsolutePath());
                        continue;
                    }
                    Files.createDirectories(targetPath.getParent());
                    if (sourceFile.isDirectory()) {
                        System.out.println("复制目录: " + sourcePath + " -> " + targetPath);
                    }
                    Files.createDirectories(targetPath.getParent());
                    copyFile(sourceFile, targetFile);
                } else if (change.getType() == SVNLogEntryPath.TYPE_DELETED) {
                    if (targetFile.exists()) {
                        if (targetFile.isDirectory()) {
                            System.out.println("删除目录: " + targetPath);
                        }
                        rmDirs(targetFile);
                        git.rm().addFilepattern(".").addFilepattern(contentPath).call();
                        git.rm().setCached(true).addFilepattern(".").addFilepattern(contentPath).call();
                    }
                }
            }

            System.out.println("提交分支：" + branch);
            git.add().addFilepattern(".").call();
            git.add().setUpdate(true).addFilepattern(".").call();
            Status status = git.status().call();
            Set<String> untracked = status.getUntracked();
            if (untracked.size() > 0) {
                System.out.println("untracked: " + untracked);
            }
            if ("".equals(commitMsg)) {
                git.commit().setMessage("SVN vision " + version).call();
            } else {
                git.commit().setMessage("SVN vision " + version + ": " + commitMsg).call();
            }
            // 修正新分支内容
            if (isNewBranch) {
                // 删除 gitRepoPath 下所有非 .git 目录和文件
                File gitRepo = new File(gitRepoPath);
                File[] files = gitRepo.listFiles();
                if (files != null) {
                    for (File file : files) {
                        if (!DELETE_WITELIST.contains(file.getName())) {
                            rmDirs(file);
                            git.rm().addFilepattern(".").addFilepattern(file.getName()).call();
                            git.rm().setCached(true).addFilepattern(".").addFilepattern(file.getName()).call();
                        }
                    }
                }
                // 拷贝 svnRepoPath 下所有非 .svn 目录和文件到 gitRepoPath 目录下
                File svnRepo = new File(svnRepoPath + File.separator + branch);
                files = svnRepo.listFiles();
                if (files != null) {
                    for (File file : files) {
                        if (file.isDirectory()) {
                            System.out.println("复制目录: " + file.getAbsolutePath() + " -> " + gitRepoPath + File.separator + file.getName());
                        }
                        copyFile(file, new File(gitRepoPath + File.separator + file.getName()));
                        git.add().addFilepattern(".").addFilepattern(file.getName()).call();
                    }
                }
                status = git.status().call();
                untracked = status.getUntracked();
                if (untracked.size() > 0) {
                    System.out.println("untracked: " + untracked);
                }
                git.commit().setMessage("SVN vision " + version + " new branch fix").call();
            }
        }
        Files.write(Paths.get(gitRepoPath, ".svn_version"), String.valueOf(version).getBytes(), StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
    }

    /**
     * 检出或创建新分支
     *
     * @param branch 目标分支
     * @return 是否创建新分支
     */
    private static boolean checkoutOrCreateBranch(Git git, String branch) throws GitAPIException, IOException {
        String currentBranch = git.getRepository().getBranch();
        if (currentBranch.equals(branch)) {
            return false;
        }
        try {
            git.checkout().setName(branch).call();
            return false;
        } catch (RefNotFoundException e) {
            // git.checkout().setCreateBranch(true).setName(branch).setUpstreamMode(CreateBranchCommand.SetupUpstreamMode.TRACK).setStartPoint("origin/" + branch).call();
            git.checkout().setCreateBranch(true).setName(branch).call();
            return true;
        }
    }

    private static void copyFile(File source, File target) throws IOException {
        if (source.isDirectory()) {
            if (!target.exists()) {
                target.mkdir();
            }
            for (File file : source.listFiles()) {
                copyFile(file, new File(target, file.getName()));
            }
        } else {
            try (FileInputStream fis = new FileInputStream(source);
                 FileOutputStream fos = new FileOutputStream(target);
                 FileChannel inputChannel = fis.getChannel();
                 FileChannel outputChannel = fos.getChannel()) {
                outputChannel.transferFrom(inputChannel, 0, inputChannel.size());
            }
        }
    }

    public static boolean rmDirs(File file) throws IOException {
        File[] fileArr = file.listFiles();
        if (fileArr != null) {
            for (File files : fileArr) {
                if (files.isDirectory()) {
                    rmDirs(files);
                } else {
                    Files.deleteIfExists(files.toPath());
                }
            }
        }
        return Files.deleteIfExists(file.toPath());
    }
}
