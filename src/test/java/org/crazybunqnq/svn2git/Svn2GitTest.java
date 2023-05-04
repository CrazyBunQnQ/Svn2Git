package org.crazybunqnq.svn2git;

import org.crazybunqnq.entity.MergedSVNLogEntry;
import org.eclipse.jgit.api.Git;
import org.eclipse.jgit.api.RmCommand;
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

import javax.mail.*;
import javax.mail.internet.InternetAddress;
import javax.mail.internet.MimeMessage;
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

    private final String USERNAME = "junjie";
    private final String PASSWORD = "junjie@20230301";
    private final String LOG_FILE_PATH = "svn_commit.log";

    private static Map<String, String> emailMap = new HashMap<>();

    private static final List<String> DELETE_WITELIST = Arrays.asList(new String[]{".git", ".idea", ".gitignore", ".svn_version", "svn_commit.log", ".svn_path", ".fix_version", "svn_git_map.properties"});
    private static final List<String> BRANCH_WITELIST = Arrays.asList(new String[]{"platform-divider"});
    private static final long FORCE_FIX_VERSION_INTERVAL = 1000;
    private static final String FORCE_FIX_VERSION_FILE = ".fix_version";
    private static Map<String, Long> lastFixVersion;
    private static final String MODEL_MAP_FILE = "svn_git_map.properties";
    private static Map<String, Map<String, Object>> modelMap = null;
    private static final List<String> MODEL_BLACKLIST = Arrays.asList(new String[]{"master", "DemoCenter"});
    private static final List<String> COPY_BLACKLIST = Arrays.asList(new String[]{".svn"});


    static {
        emailMap.put("baozi", "baozi@qq.com");
    }

    @Test
    public void syncSvnCommitTest() throws SVNException, IOException {
        // final String svnUrl = "https://192.168.0.182:8443/repo/codes/SafeMg/SMPlatform/branches";
        // final String svnRepoPath = "F:\\SvnRepo\\Platform";
        // final String gitRepoPath = "F:\\GitRepo\\Platform";
        // final Pattern dirRegx = Pattern.compile(".*/branches/([^/]+).*");
        final String svnUrl = "https://192.168.0.182:8443/repo/codes/SafeMg/Singularity";
        final String svnRepoPath = "F:\\SvnRepo\\Singularity";
        final String gitRepoPath = "F:\\GitRepo\\Singularity";
        final Pattern dirRegx = Pattern.compile(".*/Singularity/([^/]+).*");
        syncSvnCommit2Git(svnUrl, svnRepoPath, gitRepoPath, dirRegx);
    }

    @Test
    public void getSvnCommitLogTest() throws SVNException, IOException {
        final String svnUrl = "https://192.168.0.182:8443/repo/codes/SafeMg/Singularity";
        final String gitRepoPath = "F:\\GitRepo\\Singularity";

        lastFixVersion = readFixVersion(gitRepoPath + File.separator + FORCE_FIX_VERSION_FILE);
        modelMap = readModelMap(gitRepoPath + File.separator + MODEL_MAP_FILE);
        // 1. 获取 svn 仓库
        SVNRepository repository = setupSvnRepository(svnUrl, USERNAME, PASSWORD);
        // 2. 获取 svn 仓库的提交记录
        List<SVNLogEntry> svnLogEntries = getSvnLogEntries(repository);
        // 3. 合并连续的提交记录
        List<MergedSVNLogEntry> mergedLogEntries = mergeConsecutiveCommits(svnLogEntries);
        // 4. 将合并后的提交记录写入文件
        writeSvnLogEntriesToFile(mergedLogEntries, gitRepoPath + File.separator + LOG_FILE_PATH);
    }

    @Test
    public void updateSvnTest() throws IOException {
        final String svnRepoPath = "F:\\SvnRepo\\Singularity";
        final String gitRepoPath = "F:\\GitRepo\\Singularity";
        modelMap = readModelMap(gitRepoPath + File.separator + MODEL_MAP_FILE);

        long revision = readRevisionFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, 2264L);
        long startTime;
        String author = readAuthorFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, revision);
        String commitMsg = readMessageFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, revision);
        System.out.println("开始更新 svn 版本到 " + revision + "，作者 " + author + "，提交信息 " + commitMsg);
        startTime = System.currentTimeMillis();
        try {
            updateSvnToRevision(svnRepoPath, revision);
            System.out.println("    svn 更新完成, 耗时 " + (System.currentTimeMillis() - startTime) / 1000 + " 秒");
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(1);
        }
    }

    @Test
    public void readChangesByBranchFromLogFileTest() throws IOException {
        final String svnRepoPath = "F:\\SvnRepo\\Singularity";
        final String gitRepoPath = "F:\\GitRepo\\Singularity";
        final Pattern dirRegx = Pattern.compile(".*/Singularity/([^/]+).*");
        long revision = 2252L;
        modelMap = readModelMap(gitRepoPath + File.separator + MODEL_MAP_FILE);

        Map<String, List<SVNLogEntryPath>> changesByBranch = readChangesByBranchFromLogFile(svnRepoPath, gitRepoPath + File.separator + LOG_FILE_PATH, revision, dirRegx, modelMap);
        System.out.println("涉及 " + changesByBranch.size() + " 个分支到");
    }

    @Test
    public void commit2GitTest() throws IOException, SVNException {
        final String svnRepoPath = "F:\\SvnRepo\\Singularity";
        final String gitRepoPath = "F:\\GitRepo\\Singularity";
        final Pattern dirRegx = Pattern.compile(".*/Singularity/([^/]+).*");
        modelMap = readModelMap(gitRepoPath + File.separator + MODEL_MAP_FILE);
        lastFixVersion = readFixVersion(gitRepoPath + File.separator + FORCE_FIX_VERSION_FILE);

        long revision = readRevisionFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, 2264L);
        long startTime;

        String author = readAuthorFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, revision);
        String commitMsg = readMessageFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, revision);
        startTime = System.currentTimeMillis();
        Map<String, List<SVNLogEntryPath>> changesByBranch = readChangesByBranchFromLogFile(svnRepoPath, gitRepoPath + File.separator + LOG_FILE_PATH, revision, dirRegx, modelMap);

        System.out.println("开始提交 " + changesByBranch.size() + " 个分支到 Git");
        try {
            long gitCommitStartTime = System.currentTimeMillis();
            copySvnChangesToGit(svnRepoPath, gitRepoPath, changesByBranch, revision, author, commitMsg, modelMap);
            System.out.println("    提交 " + revision + " 版本资源到 Git 耗时：" + (System.currentTimeMillis() - gitCommitStartTime) / 1000 + " 秒");
            System.out.println("同步 " + revision + " 版本到 Git 总耗时：" + (System.currentTimeMillis() - startTime) / 1000 + " 秒\n");
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(1);
        }
    }

    public void syncSvnCommit2Git(String svnUrl, String svnRepoPath, String gitRepoPath, Pattern dirRegx) throws SVNException, IOException {
        lastFixVersion = readFixVersion(gitRepoPath + File.separator + FORCE_FIX_VERSION_FILE);
        modelMap = readModelMap(gitRepoPath + File.separator + MODEL_MAP_FILE);
        // 1. 获取 svn 仓库
        SVNRepository repository = setupSvnRepository(svnUrl, USERNAME, PASSWORD);
        // 2. 获取 svn 仓库的提交记录
        List<SVNLogEntry> svnLogEntries = getSvnLogEntries(repository);
        // 3. 合并连续的提交记录
        List<MergedSVNLogEntry> mergedLogEntries = mergeConsecutiveCommits(svnLogEntries);
        // 4. 将合并后的提交记录写入文件
        writeSvnLogEntriesToFile(mergedLogEntries, gitRepoPath + File.separator + LOG_FILE_PATH);
        long revision = readRevisionFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, null);
        long startTime;
        while (revision > 0) {
            Long curSvnVersionInGit = getCurrentSvnVersionFromGit(gitRepoPath);
            revision = readRevisionFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, curSvnVersionInGit);
            String author = readAuthorFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, revision);
            String commitMsg = readMessageFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, revision);
            System.out.println("开始更新 svn 版本到 " + revision + "，作者 " + author + "，提交信息 " + commitMsg);
            startTime = System.currentTimeMillis();
            try {
                updateSvnToRevision(svnRepoPath, revision);
                System.out.println("    svn 更新完成, 耗时 " + (System.currentTimeMillis() - startTime) / 1000 + " 秒");
            } catch (Exception e) {
                e.printStackTrace();
                System.exit(1);
            }
            Map<String, List<SVNLogEntryPath>> changesByBranch = readChangesByBranchFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, revision, dirRegx);
            System.out.println("开始提交 " + changesByBranch.size() + " 个分支到 Git");
            try {
                long gitCommitStartTime = System.currentTimeMillis();
                copySvnChangesToGit(svnRepoPath, gitRepoPath, changesByBranch, revision, author, commitMsg, null);
                System.out.println("    提交 " + revision + " 版本资源到 Git 耗时：" + (System.currentTimeMillis() - gitCommitStartTime) / 1000 + " 秒");
                System.out.println("同步 " + revision + " 版本到 Git 总耗时：" + (System.currentTimeMillis() - startTime) / 1000 + " 秒\n");
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

    private Map<String, List<SVNLogEntryPath>> readChangesByBranchFromLogFile(String svnRepoPath, String filePath, long revision, Pattern dirRegx, Map<String, Map<String, Object>> modelMap) throws IOException {
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
                        String model = getBranchFromPath(entryPath.getPath(), dirRegx);
                        String branch = null;
                        if (MODEL_BLACKLIST.contains(model)) {
                            continue;
                        }
                        // 通过 Map 获取分支
                        if (modelMap.containsKey(model)) {
                            Map<String, Object> regxMap = modelMap.get(model);
                            String regxStr = (String) regxMap.get("str");
                            Pattern branchRegx = (Pattern) regxMap.get("regx");
                            Matcher matcher = branchRegx.matcher(line);
                            // TODO 独立模块在提交时再说
                            if (!regxStr.startsWith("new:") && matcher.find()) {
                                branch = matcher.group(1);
                                if (!changesByBranch.containsKey(branch)) {
                                    System.out.println("涉及分支: " + branch);
                                }
                            } else if (!regxStr.startsWith("new:")) {
                                // 只可能是模块或分支目录，排除删除类型
                                if (line.charAt(0) == 'D') {
                                    continue;
                                }
                                // 遍历文件夹，全量添加分支
                                String modelPath = svnRepoPath + File.separator + model;
                                File modelDir = new File(modelPath);
                                File[] modelBranchDirs = modelDir.listFiles();
                                for (File modelBranchDir : modelBranchDirs) {
                                    branch = modelBranchDir.getName();

                                    String realModelName = getRealModelName(model, modelBranchDir);
                                    if (realModelName == null) {
                                        continue;
                                    }
                                    String realModelPath = entryPath.getPath().substring(0, entryPath.getPath().indexOf(model) + model.length()) + "/" + branch + "/" + realModelName;
                                    SVNLogEntryPath newEntryPath = new SVNLogEntryPath(realModelPath, line.charAt(0), null, revision);
                                    if (!changesByBranch.containsKey(branch)) {
                                        System.out.println("涉及分支: " + branch);
                                    }
                                    // changesByBranch.computeIfAbsent(branch, k -> new ArrayList<>()).add(newEntryPath);
                                    changesByBranch.computeIfAbsent(branch, k -> new ArrayList<>());
                                    List<SVNLogEntryPath> entryPaths = changesByBranch.get(branch);
                                    if (!entryPaths.contains(newEntryPath)) {
                                        entryPaths.add(newEntryPath);
                                    }
                                }
                                continue;
                            }
                        } else {
                            try {
                                sendMail("Svn2Git", "发现新模块: " + model + "\n及时确认是否需要添加映射");
                            } catch (Exception ignored) {
                            }
                            // TODO 添加映射
                            System.out.println("发现新模块: " + model);
                            continue;
                        }
                        // changesByBranch.computeIfAbsent(branch, k -> new ArrayList<>()).add(entryPath);
                        changesByBranch.computeIfAbsent(branch, k -> new ArrayList<>());
                        List<SVNLogEntryPath> entryPaths = changesByBranch.get(branch);
                        if (!entryPaths.contains(entryPath)) {
                            entryPaths.add(entryPath);
                        }
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
    private static void copySvnChangesToGit(String svnRepoPath, String gitRepoPath, Map<String, List<SVNLogEntryPath>> changesByBranch, long version, String author, String commitMsg, Map<String, Map<String, Object>> modelMap) throws IOException, GitAPIException {
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
                if (modelMap == null) {
                    System.out.println("    跳过分支：" + branch);
                    continue;
                }
            }
            // TODO 暂时跳过 branch == null
            if (branch == null) {
                continue;
            }
            boolean isNewBranch = checkoutOrCreateBranch(git, branch);

            long lastVersion = lastFixVersion != null && lastFixVersion.containsKey(branch) ? lastFixVersion.get(branch) : 0;
            if (!isNewBranch && version - lastVersion > FORCE_FIX_VERSION_INTERVAL) {
                System.out.println("    分支 " + branch + " 距离上次全量提交的版本间隔太久，强制全量提交");
                isNewBranch = true;
            }

            long starttime = System.currentTimeMillis();
            if (!isNewBranch) {
                List<SVNLogEntryPath> svnLogEntryPaths = changesByBranch.get(branch);
                for (SVNLogEntryPath change : svnLogEntryPaths) {
                    // 从 change.getPath() 中截取 branch 之后的部分
                    String path = change.getPath();

                    String model = null;
                    String realModelName;
                    // 分支之后的路径
                    String branchPath = path.substring(path.indexOf(branch));
                    String contentPath = null;
                    Path targetPath = null;
                    String regxStr = null;
                    if (modelMap == null) {
                        // 跳过分支根目录
                        if (branchPath.length() == branch.length()) {
                            continue;
                        }
                        contentPath = branchPath.substring(branchPath.indexOf(branch) + branch.length() + 1);
                        targetPath = Paths.get(gitRepoPath, contentPath);
                    } else {
                        model = path.substring(path.indexOf(gitRepoName) + gitRepoName.length() + 1);
                        if (model != null && model.contains("/")) {
                            model = model.substring(0, model.indexOf("/"));
                        }
                        if (modelMap.containsKey(model)) {
                            regxStr = (String) modelMap.get(model).get("str");
                            if (regxStr.startsWith("new:")) {
                                // TODO
                                System.out.println("独立模块");
                                continue;
                            } else {
                                realModelName = getRealModelName(model, new File(svnRepoPath + File.separator + model + File.separator + branch));
                                if (realModelName == null) {
                                    continue;
                                }
                                // 跳过分支根目录
                                if (branchPath.length() == branch.length() + realModelName.length() + 1) {
                                    continue;
                                }
                                contentPath = branchPath.substring(branchPath.indexOf(branch) + branch.length() + realModelName.length() + 1);
                                targetPath = Paths.get(gitRepoPath, model, contentPath);
                            }
                        }
                    }

                    File targetFile = targetPath.toFile();
                    if (change.getType() == SVNLogEntryPath.TYPE_ADDED || change.getType() == SVNLogEntryPath.TYPE_MODIFIED) {
                        Path sourcePath = model == null ? Paths.get(svnRepoPath, branchPath) : Paths.get(svnRepoPath, model, branchPath);
                        File sourceFile = sourcePath.toFile();
                        if (!sourceFile.exists()) {
                            System.out.println("        Source file not exist or source file is directory: " + sourceFile.getAbsolutePath());
                            continue;
                        }
                        Files.createDirectories(targetPath.getParent());
                        if (sourceFile.isDirectory()) {
                            System.out.println("        复制目录: " + sourcePath + " -> " + targetPath);
                        }
                        Files.createDirectories(targetPath.getParent());
                        copyFile(sourceFile, targetFile);
                    } else if (change.getType() == SVNLogEntryPath.TYPE_DELETED) {
                        if (targetFile.exists()) {
                            if (targetFile.isDirectory()) {
                                System.out.println("        删除目录: " + targetPath);
                            }
                            rmDirs(targetFile);
                        }
                    }
                }
                // 从 master 分支检出 .gitignore 文件
                if (!"master".equals(branch)) {
                    git.checkout().addPath(".gitignore").setStartPoint("master").call();
                }
                long costtime = (System.currentTimeMillis() - starttime) / 1000;
                if (costtime > 2L) {
                    System.out.println("        " + branch + " 分支修改和删除文件耗时：" + costtime + " 秒");
                }
                starttime = System.currentTimeMillis();
                git.add().addFilepattern(".").call();
                git.rm().setCached(true).addFilepattern(".").call();
                Status status = git.status().call();
                Set<String> untracked = status.getUntracked();
                Set<String> modified = status.getModified();
                Set<String> removed = status.getRemoved();
                Set<String> missing = status.getMissing();
                if (missing.size() > 0) {
                    RmCommand rm = git.rm();
                    for (String missingFile : missing) {
                        rm.addFilepattern(missingFile);
                    }
                    rm.call();
                }
                System.out.println("        " + branch + " 分支 git add . 耗时：" + (System.currentTimeMillis() - starttime) / 1000 + " 秒");
                if (untracked.size() > 0 || modified.size() > 0 || removed.size() > 0) {
                    try {
                        sendMail("Svn2Git", svnRepoPath + " " + version + " 版本存在未跟踪文件");
                    } catch (Exception ignored) {
                    }
                    System.out.println("        untracked: " + untracked);
                }
                if ("".equals(commitMsg)) {
                    git.commit().setMessage("SVN vision " + version).call();
                } else {
                    git.commit().setMessage("SVN vision " + version + ": " + commitMsg).call();
                }
            } else {
                // 修正新分支内容
                // 删除 gitRepoPath 下所有非 .git 目录和文件
                File gitRepo = new File(gitRepoPath);
                File[] files = gitRepo.listFiles();
                if (files != null) {
                    for (File file : files) {
                        String fileName = file.getName();
                        if (!DELETE_WITELIST.contains(fileName)) {
                            System.out.println("        删除目录: " + file.getAbsolutePath());
                            rmDirs(file);
                        }
                    }
                }
                // 拷贝 svnRepoPath 下所有非 .svn 目录和文件到 gitRepoPath 目录下
                File svnRepo = modelMap == null ? new File(svnRepoPath + File.separator + branch) : new File(svnRepoPath);
                files = svnRepo.listFiles();
                if (files != null) {
                    for (File file : files) {
                        String fileName = file.getName();
                        if (COPY_BLACKLIST.contains(fileName)) {
                            continue;
                        }
                        if (modelMap == null) {
                            if (file.isDirectory()) {
                                System.out.println("        复制目录: " + file.getAbsolutePath() + " -> " + gitRepoPath + File.separator + fileName);
                            }
                            copyFile(file, new File(gitRepoPath + File.separator + fileName));
                        } else {
                            if (modelMap.containsKey(fileName)) {
                                Map<String, Object> regxMap = modelMap.get(fileName);
                                String regxStr = (String) regxMap.get("str");
                                if (regxStr.startsWith("new:")) {
                                    // TODO 同步独立模块
                                    System.out.println("        独立模块: " + fileName);
                                } else {
                                    String realModelName = getRealModelName(fileName, new File(file.getAbsolutePath() + File.separator + branch));
                                    if (realModelName == null) {
                                        continue;
                                    }
                                    file = new File(file.getAbsolutePath() + File.separator + branch + File.separator + realModelName);
                                    if (file.isDirectory()) {
                                        System.out.println("        复制目录: " + file.getAbsolutePath() + " -> " + gitRepoPath + File.separator + fileName);
                                    }
                                    copyFile(file, new File(gitRepoPath + File.separator + fileName));
                                }
                            } else if (file.isDirectory()) {
                                // TODO 未知模块
                                System.out.println("        未知模块: " + fileName);
                            } else {
                                System.out.println("        复制文件: " + file.getAbsolutePath() + " -> " + gitRepoPath + File.separator + fileName);
                                copyFile(file, new File(gitRepoPath + File.separator + fileName));
                            }
                        }
                    }
                }
                // 从 master 分支检出 .gitignore 文件
                if (!"master".equals(branch)) {
                    git.checkout().addPath(".gitignore").setStartPoint("master").call();
                }
                long costtime = (System.currentTimeMillis() - starttime) / 1000;
                if (costtime > 2L) {
                    System.out.println("        " + branch + " 分支修改和删除文件耗时：" + costtime + " 秒");
                }
                starttime = System.currentTimeMillis();
                git.rm().setCached(true).addFilepattern(".").call();
                git.add().addFilepattern(".").call();
                Status status = git.status().call();
                Set<String> untracked = status.getUntracked();
                Set<String> modified = status.getModified();
                Set<String> removed = status.getRemoved();
                Set<String> missing = status.getMissing();
                if (missing.size() > 0) {
                    RmCommand rm = git.rm();
                    for (String missingFile : missing) {
                        rm.addFilepattern(missingFile);
                    }
                    rm.call();
                }
                System.out.println("        " + branch + " 分支 git add . 耗时：" + (System.currentTimeMillis() - starttime) / 1000 + " 秒");
                if (untracked.size() > 0 || modified.size() > 0 || removed.size() > 0) {
                    try {
                        sendMail("Svn2Git", svnRepoPath + " " + version + " 版本存在未跟踪文件");
                    } catch (Exception ignored) {
                    }
                    System.out.println("        untracked: " + untracked);
                }
                // git.commit().setMessage("SVN vision " + version + " new branch fix").call();
                if ("".equals(commitMsg)) {
                    git.commit().setMessage("SVN vision " + version).call();
                } else {
                    git.commit().setMessage("SVN vision " + version + ": " + commitMsg).call();
                }
                lastFixVersion.put(branch, version);
                writeFixVersion(gitRepoPath + File.separator + FORCE_FIX_VERSION_FILE, lastFixVersion);
            }
        }
        git.close();
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
        System.out.println("    当前分支：" + currentBranch + ", 目标分支：" + branch);
        if (currentBranch.equals(branch)) {
            return false;
        }
        try {
            git.checkout().setName(branch).call();
            return false;
        } catch (RefNotFoundException e) {
            try {
                sendMail("Svn2Git", git.getRepository().toString() + " 将要创建新分支: " + branch);
            } catch (Exception ignored) {
            }
            System.out.println("    创建新分支：" + branch);
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

    public static Map<String, Map<String, Object>> readModelMap(String filePath) {

        try (Scanner scanner = new Scanner(new File(filePath))) {
            Map<String, Map<String, Object>> modelMap = new HashMap<>();
            while (scanner.hasNextLine()) {
                Map<String, Object> map = new HashMap<>(2);
                String line = scanner.nextLine();
                String[] parts = line.split("=");
                String branch = parts[0];
                String pathReg = parts[1];
                map.put("str", pathReg);
                if (pathReg.startsWith("new:")) {
                    pathReg = pathReg.substring(4);
                }
                map.put("regx", Pattern.compile(pathReg));
                modelMap.put(branch, map);
            }
            return modelMap;
        } catch (FileNotFoundException e) {
            System.out.println("File not found: " + filePath);
        }

        return null;
    }

    private static String getRealModelName(String model, File modelBranchDir) {
        File[] files = modelBranchDir.listFiles();
        if (files == null) {
            return null;
        }
        for (File file : files) {
            if (model.toLowerCase().equals(file.getName().toLowerCase())) {
                return file.getName();
            }
        }
        return null;
    }

    public static void sendMail(String title, String content) throws Exception {
        String host = "smtp.qq.com";
        String sender = "sender@qq.com";
        String recipient = "recipient@qq.com";
        String authCode = "授权码";

        Properties props = new Properties();
        props.put("mail.smtp.host", host);
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.ssl.enable", "true");

        Session session = Session.getInstance(props, new Authenticator() {
            protected PasswordAuthentication getPasswordAuthentication() {
                return new PasswordAuthentication(sender, authCode);
            }
        });

        Message message = new MimeMessage(session);
        message.setFrom(new InternetAddress(sender));
        message.setRecipient(Message.RecipientType.TO, new InternetAddress(recipient));
        message.setSubject(title);

        message.setContent(content, "text/html;charset=UTF-8");

        Transport.send(message);
    }

    public static Map<String, Long> readFixVersion(String filePath) {
        Map<String, Long> lastFixVersion = new HashMap<>();

        try (Scanner scanner = new Scanner(new File(filePath))) {
            while (scanner.hasNextLine()) {
                String line = scanner.nextLine();
                String[] parts = line.split("=");
                String branch = parts[0];
                long version = Long.parseLong(parts[1]);
                lastFixVersion.put(branch, version);
            }
        } catch (FileNotFoundException e) {
            System.out.println("File not found: " + filePath);
        } catch (NumberFormatException e) {
            // handle number format error
            System.out.println("Invalid version number");
        }

        return lastFixVersion;
    }

    public static void writeFixVersion(String filePath, Map<String, Long> lastFixVersion) {
        try (FileWriter fileWriter = new FileWriter(filePath); BufferedWriter writer = new BufferedWriter(fileWriter)) {
            for (Map.Entry<String, Long> entry : lastFixVersion.entrySet()) {
                writer.write(entry.getKey() + "=" + entry.getValue());
                writer.newLine();
            }
        } catch (IOException e) {
            // handle IO error
            System.out.println("Error writing to file");
        }
    }
}
