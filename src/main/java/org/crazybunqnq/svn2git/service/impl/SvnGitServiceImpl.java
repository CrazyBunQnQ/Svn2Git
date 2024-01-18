package org.crazybunqnq.svn2git.service.impl;

import org.apache.commons.exec.CommandLine;
import org.apache.commons.exec.DefaultExecutor;
import org.crazybunqnq.svn2git.config.UserEmailMapConfig;
import org.crazybunqnq.svn2git.entity.MergedSVNLogEntry;
import org.crazybunqnq.svn2git.service.ISvnGitService;
import org.eclipse.jgit.api.*;
import org.eclipse.jgit.api.errors.GitAPIException;
import org.eclipse.jgit.api.errors.RefNotFoundException;
import org.eclipse.jgit.lib.PersonIdent;
import org.eclipse.jgit.lib.StoredConfig;
import org.eclipse.jgit.transport.CredentialsProvider;
import org.eclipse.jgit.transport.FetchResult;
import org.eclipse.jgit.transport.UsernamePasswordCredentialsProvider;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.tmatesoft.svn.core.SVNException;
import org.tmatesoft.svn.core.SVNLogEntry;
import org.tmatesoft.svn.core.SVNLogEntryPath;
import org.tmatesoft.svn.core.SVNURL;
import org.tmatesoft.svn.core.auth.ISVNAuthenticationManager;
import org.tmatesoft.svn.core.io.SVNRepository;
import org.tmatesoft.svn.core.io.SVNRepositoryFactory;
import org.tmatesoft.svn.core.wc.SVNWCUtil;

import javax.mail.*;
import javax.mail.internet.InternetAddress;
import javax.mail.internet.MimeMessage;
import java.io.*;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import static org.tmatesoft.svn.core.SVNLogEntryPath.*;

@Service
public class SvnGitServiceImpl implements ISvnGitService {
    private static final Logger logger = LoggerFactory.getLogger(SvnGitServiceImpl.class);
    private static final SimpleDateFormat SIMPLE_DATE_FORMAT = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
    private static final String LOG_FILE_PATH = "svn_commit.log";
    private static final String FORCE_FIX_VERSION_FILE = ".fix_version";
    private static final String MODEL_MAP_FILE = "svn_git_map.properties";
    private static final long FORCE_FIX_VERSION_INTERVAL = 1000;
    private static final List<String> DELETE_WITELIST = Arrays.asList(new String[]{".git", ".idea", ".gitignore", ".svn_version", "svn_commit.log", ".svn_path", ".fix_version", "svn_git_map.properties", "hooks", "README.md", "config.bat", "config.sh"});
    private static final List<String> BRANCH_WITELIST = Arrays.asList(new String[]{"platform-divider", "dev"});
    private static final Pattern BRANCH_REGEX = Pattern.compile("\\d+\\.\\d+.*");
    private static final List<String> MODEL_BLACKLIST = Arrays.asList(new String[]{".git", ".idea", "master", "DemoCenter", "src", "target", ".settings", "datacollector", "eacenter", "DdataCleaner", ".metadata", "hooks", "SoarCenter", "SoarApp", "VirusCenter", "LogAudit", "Common", "Package"});
    private static final List<String> BRANCH_BLACKLIST = Arrays.asList(new String[]{".svn", ".metadata", "Common", "transceiver"});
    private static final List<String> COPY_BLACKLIST = Arrays.asList(new String[]{".svn", ".metadata", ".git"});
    private static Set<String> newModel = new HashSet<>(20);
    public static int STATUS = 0;

    @Value("${svn.username}")
    private String username;
    @Value("${svn.password}")
    private String password;
    @Value("${git.username}")
    private String gitUserName;
    @Value("${git.password}")
    private String gitPassword;

    @Value("${mail.sender}")
    private String sender;
    @Value("${mail.recipient}")
    private String recipient;
    @Value("${mail.password}")
    private String authCode;
    @Value("${mail.host}")
    private String host;
    @Autowired
    private UserEmailMapConfig userEmailMap;

    @Override
    public void test() {
        if (STATUS != 0) {
            return;
        }
        STATUS = 1;
        try {
            Thread.sleep(1000 * 90);
        } catch (InterruptedException e) {
            throw new RuntimeException(e);
        }
        STATUS = 0;
    }

    @Override
    @Async("syncSvnToGitExecutor")
    public void syncSvnCommit2Git(String svnUrl, String svnRepoPath, String gitRepoPath, Pattern dirRegx, String suffix) {
        if (STATUS != 0) {
            logger.info("同步正在进行中...");
            return;
        }
        STATUS = 1;

        Map<String, Map<String, Object>> modelMap = readModelMap(gitRepoPath + File.separator + MODEL_MAP_FILE);
        SVNRepository repository;
        try {
            // 1. 获取 svn 仓库
            repository = setupSvnRepository(svnUrl, username, password);
            // 2. 获取 svn 仓库的提交记录
            List<SVNLogEntry> svnLogEntries = getSvnLogEntries(repository);
            // 3. 合并连续的提交记录
            List<MergedSVNLogEntry> mergedLogEntries = mergeConsecutiveCommits(svnLogEntries);
            // 4. 将合并后的提交记录写入文件
            writeSvnLogEntriesToFile(mergedLogEntries, gitRepoPath);
            long revision = readRevisionFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, null);
            long startTime;
            while (revision > 0) {
                Long curSvnVersionInGit = getCurrentSvnVersionFromGit(gitRepoPath);
                revision = readRevisionFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, curSvnVersionInGit);
                if (revision < 0) {
                    logger.info(svnRepoPath + " 项目在 " + curSvnVersionInGit + " 版本之后没有需要同步的提交记录");
                    break;
                }
                String author = readAuthorFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, revision);
                String commitMsg = readMessageFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, revision);
                Date commitDate = readDateFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, revision);
                logger.info("开始更新 svn 项目 " + svnRepoPath + " 到 " + revision + " 版本，作者 " + author + "，提交信息 " + commitMsg + "，提交时间 " + SIMPLE_DATE_FORMAT.format(commitDate));
                startTime = System.currentTimeMillis();
                try {
                    int updateResult = updateSvnToRevision(svnRepoPath, revision);
                    if (updateResult != 0) {
                        logger.error("    svn 更新失败, 耗时 " + (System.currentTimeMillis() - startTime) / 1000 + " 秒");
                        System.exit(1);
                    }
                    logger.info("    svn 更新完成, 耗时 " + (System.currentTimeMillis() - startTime) / 1000 + " 秒");
                } catch (Exception e) {
                    try {
                        sendMail("Svn2Git", "svn 项目 " + svnRepoPath + " 更新失败: " + e.getMessage());
                    } catch (Exception ignored) {
                    }
                    e.printStackTrace();
                    // 退出应用
                    System.exit(1);
                }
                Map<String, List<SVNLogEntryPath>> changesByBranch;
                if (modelMap == null) {
                    changesByBranch = readChangesByBranchFromLogFile(gitRepoPath + File.separator + LOG_FILE_PATH, revision, dirRegx);
                } else {
                    changesByBranch = readChangesByBranchFromLogFile(svnRepoPath, gitRepoPath + File.separator + LOG_FILE_PATH, revision, dirRegx, modelMap);
                }
                logger.info("开始提交 " + changesByBranch.size() + " 个分支到 Git");
                try {
                    long gitCommitStartTime = System.currentTimeMillis();
                    copySvnChangesToGit(svnRepoPath, gitRepoPath, changesByBranch, revision, author, commitMsg, commitDate, modelMap, modelMap != null, dirRegx, suffix);
                    logger.info("    提交 " + revision + " 版本资源到 Git 耗时：" + (System.currentTimeMillis() - gitCommitStartTime) / 1000 + " 秒");
                    logger.info("同步 " + svnRepoPath + " 项目 " + revision + " 版本到 Git 总耗时：" + (System.currentTimeMillis() - startTime) / 1000 + " 秒\n");
                } catch (Exception e) {
                    e.printStackTrace();
                    System.exit(1);
                }
                modelMap = readModelMap(gitRepoPath + File.separator + MODEL_MAP_FILE);
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        } catch (SVNException e) {
            throw new RuntimeException(e);
        } finally {
            STATUS = 0;
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
                String message = previousEntry.getMessage();
                if (message != null && !message.isEmpty() && !message.endsWith("; ")) {
                    message += "; ";
                }
                previousEntry.setMessage(message + "\n" + logEntry.getMessage());

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
     * @param gitRepoPath
     * @throws IOException
     */
    private void writeSvnLogEntriesToFile(List<MergedSVNLogEntry> logEntries, String gitRepoPath) throws IOException {
        String logFilePath = gitRepoPath + File.separator + LOG_FILE_PATH;
        String gitRepoName = gitRepoPath.substring(gitRepoPath.lastIndexOf(File.separator) + 1);
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(logFilePath))) {
            for (MergedSVNLogEntry logEntry : logEntries) {
                writer.write("Revision: " + logEntry.getRevision() + "\n");
                writer.write("Author: " + logEntry.getAuthor() + "\n");
                writer.write("Date: " + SIMPLE_DATE_FORMAT.format(logEntry.getDate()) + "\n");
                writer.write("Message: " + logEntry.getMessage() + "\n");

                writer.write("Changed Paths:\n");
                for (Map.Entry<String, SVNLogEntryPath> entry : logEntry.getChangedPaths().entrySet()) {
                    SVNLogEntryPath entryPtah = entry.getValue();
                    if (entryPtah.getCopyPath() != null || entryPtah.getCopyRevision() > 0) {
                        writer.write(entry.getValue().getType() + "," + entry.getKey() + "," + entryPtah.getCopyPath() + "," + entryPtah.getCopyRevision() + "\n");
                    } else {
                        writer.write(entry.getValue().getType() + "," + entry.getKey() + "\n");
                    }
                }
                writer.write("\n");
            }
        }
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

    private static Date readDateFromLogFile(String filePath, long version) throws IOException {
        try (BufferedReader reader = new BufferedReader(new FileReader(filePath))) {
            String line;
            boolean targetRevisionFound = false;
            while ((line = reader.readLine()) != null) {
                if (line.startsWith("Revision:") && Long.parseLong(line.split(" ")[1]) == version) {
                    targetRevisionFound = true;
                } else if (targetRevisionFound && line.startsWith("Date: ")) {
                    return SIMPLE_DATE_FORMAT.parse(line.substring(6));
                }
            }
        } catch (ParseException ignored) {
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
    private int updateSvnToRevision(String workingCopyPath, long revision) throws IOException {
        CommandLine cmd = new CommandLine("svn");
        cmd.addArgument("update");
        cmd.addArgument("-r");
        cmd.addArgument(String.valueOf(revision));
        cmd.addArgument(workingCopyPath);
        DefaultExecutor executor = new DefaultExecutor();
        return  executor.execute(cmd);
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
                        String[] items = line.split(",");
                        SVNLogEntryPath entryPath;
                        if (items.length >= 4) {
                            entryPath = new SVNLogEntryPath(items[1], line.charAt(0), items[2], Long.parseLong(items[3]));
                        } else {
                            entryPath = new SVNLogEntryPath(items[1], line.charAt(0), null, -1);
                        }
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
                        String[] items = line.split(",");
                        SVNLogEntryPath entryPath;
                        if (items.length >= 4) {
                            entryPath = new SVNLogEntryPath(items[1], line.charAt(0), items[2], Long.parseLong(items[3]));
                        } else {
                            entryPath = new SVNLogEntryPath(items[1], line.charAt(0), null, -1);
                        }
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
                            Matcher matcher = branchRegx.matcher(entryPath.getPath());
                            // 独立模块在提交时再说
                            if (!regxStr.contains("(") || (regxStr.contains("(") && matcher.find())) {
                                if (!regxStr.contains("(")) {
                                    branch = "dev";
                                } else {
                                    branch = matcher.group(1);
                                }
                                File branchFile;
                                if ("dev".equals(branch) && !regxStr.contains("(")) {
                                    branchFile = Paths.get(svnRepoPath, model).toFile();
                                } else {
                                    branchFile = Paths.get(svnRepoPath, model, branch).toFile();
                                }
                                if (!branchFile.exists() || branchFile.isFile()) {
                                    continue;
                                }
                                if (BRANCH_BLACKLIST.contains(branch)) {
                                    logger.info("    涉及分支: " + branch + " 已被忽略");
                                    continue;
                                }
                                if (regxStr.startsWith("new:")) {
                                    branch = model + ":" + branch;
                                }
                                if (!changesByBranch.containsKey(branch)) {
                                    if (regxStr.startsWith("new:")) {
                                        logger.info("    涉及独立模块 " + model + " 分支: " + branch);
                                    } else {
                                        logger.info("    涉及分支1: " + branch);
                                    }
                                }
                            } else {
                                // 只可能是模块或分支目录，排除删除类型
                                if (entryPath.getType() == TYPE_DELETED) {
                                    continue;
                                }
                                // 遍历文件夹，全量添加分支 TODO 如果是没有分支的目录，则只取 dev 分支
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
                                    SVNLogEntryPath newEntryPath = new SVNLogEntryPath(realModelPath, line.charAt(0), null, -1L);
                                    if (regxStr.startsWith("new:")) {
                                        branch = model + ":" + branch;
                                    }
                                    if (!changesByBranch.containsKey(branch)) {
                                        if (regxStr.startsWith("new:")) {
                                            logger.info("涉及独立模块 " + model + " 分支: " + branch);
                                        } else {
                                            logger.info("涉及分支2: " + branch);
                                        }
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
                        } else if (!MODEL_BLACKLIST.contains(model)) {
                            File file = Paths.get(svnRepoPath, model).toFile();
                            if (!file.isDirectory()) {
                                continue;
                            }
                            if (!newModel.contains(model)) {
                                newModel.add(model);
                                try {
                                    sendMail("Svn2Git", "发现新模块: " + model + "\n及时确认是否需要添加映射");
                                } catch (Exception ignored) {
                                }
                                // 添加映射
                                logger.info("    发现新模块: " + model);
                            }
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
        if (pattern == null) {
            return "master";
        }
        Matcher matcher = pattern.matcher(path);
        return matcher.find() ? matcher.group(1) : "master";
    }

    private int gitAddAll(File gitRepoPath) throws IOException {
        CommandLine commandLine = CommandLine.parse("git add .");
        DefaultExecutor executor = new DefaultExecutor();
        executor.setWorkingDirectory(gitRepoPath);
        return executor.execute(commandLine);
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
    private Long copySvnChangesToGit(String svnRepoPath, String gitRepoPath, Map<String, List<SVNLogEntryPath>> changesByBranch, long version, String author, String commitMsg, Date commitDate, Map<String, Map<String, Object>> modelMap, boolean hasModel, Pattern dirRegx, String suffix) throws IOException, GitAPIException {
        Map<String, Long> lastFixVersion = readFixVersion(gitRepoPath + File.separator + FORCE_FIX_VERSION_FILE);
        File gitWorkingDir = new File(gitRepoPath);
        Git git = Git.open(gitWorkingDir);
        // 设置提交用户
        StoredConfig config = git.getRepository().getConfig();
        Map<String, String> emailMap = userEmailMap.getUserMap();
        config.setString("user", null, "name", author);
        config.setString("user", null, "email", emailMap.get(author));
        if (emailMap.get(author) == null) {
            try {
                sendMail("Svn2Git", "出现新的提交人: " + author + ", 请及时配置该用户的邮件");
            } catch (Exception ignored) {
            }
        }
        // 添加认证信息
        CredentialsProvider credentialsProvider = new UsernamePasswordCredentialsProvider(gitUserName, gitPassword);
        PersonIdent personIdent = new PersonIdent(new PersonIdent(author, emailMap.get(author)), commitDate == null ? new Date() : commitDate);
        // 将 changesByBranch 的 key 尾号进行排序
        List<String> sortedBranches = changesByBranch.keySet().stream().sorted().collect(Collectors.toList());

        Long highestVersion = 0L;
        for (String branch : sortedBranches) {
            String gitRepoName = gitRepoPath.substring(gitRepoPath.lastIndexOf(File.separator) + 1);
            if (branch.startsWith(".")) {
                continue;
            }
            if (dirRegx != null) {
                if ("master".equals(branch) || (!branch.toLowerCase().startsWith(gitRepoName.toLowerCase() + "_") && !BRANCH_REGEX.matcher(branch).matches() && !BRANCH_WITELIST.contains(branch))) {
                    if (modelMap == null) {
                        logger.info("    跳过分支：" + branch);
                        continue;
                    }
                }
            }
            // 独立模块的分支单独处理
            if (branch.contains(":")) {
                String[] tmp = branch.split(":");
                String tmpModel = tmp[0];
                String tmpBranch = tmp[1];
                Map<String, Map<String, Object>> tmpModelMap = new HashMap<>(1);
                Map<String, Object> tmpMap = new HashMap<>(2);
                String tmpStr = (String) modelMap.get(tmpModel).get("str");
                tmpMap.put("str", tmpStr.substring(tmpStr.indexOf(":") + 1));
                tmpMap.put("regx", modelMap.get(tmpModel).get("regx"));
                tmpModelMap.put(tmpModel, tmpMap);
                Map<String, List<SVNLogEntryPath>> subChangesByBranch = new HashMap<>(1);
                subChangesByBranch.put(tmpBranch, changesByBranch.get(branch));
                Long subVersion = copySvnChangesToGit(svnRepoPath + File.separator + tmpModel,
                        gitRepoPath.replace(gitRepoName, tmpModel),
                        subChangesByBranch, version, author, commitMsg, commitDate, tmpModelMap, false, null, null);
                if (subVersion != null && highestVersion > 0L) {
                    highestVersion = subVersion;
                }
                continue;
            }
            // 是否涉及合并
            boolean hasMerge = false;
            Set<String> mergeSet = new HashSet<>();
            List<SVNLogEntryPath> svnLogEntryPaths = changesByBranch.get(branch);
            try {
                for (SVNLogEntryPath change : svnLogEntryPaths) {
                    String path = change.getPath();
                    String copyPath = change.getCopyPath();
                    checkMergeAction(svnRepoPath, version, branch, mergeSet, path, copyPath);
                }
            } catch (Exception ignored) {
            }
            if (!mergeSet.isEmpty()) {
                String msg = String.join("\n", mergeSet);
                logger.info("    此版本涉及分支合并操作: \n" + msg);
                hasMerge = true;
            }
            boolean isNewBranch = checkoutOrCreateBranch(git, credentialsProvider, branch);

            long lastVersion = lastFixVersion != null && lastFixVersion.containsKey(branch) ? lastFixVersion.get(branch) : 0;
            // if (!isNewBranch && version - lastVersion > FORCE_FIX_VERSION_INTERVAL) {
                // logger.info("    分支 " + branch + " 距离上次全量提交的版本间隔太久，强制全量提交");
                // isNewBranch = true;
            // }
            if (!isNewBranch && modelMap != null && !hasModel) {
                logger.info("    模块 " + gitRepoName + " 强制全量提交");
                isNewBranch = true;
            }

            // 从 master 分支检出 .gitignore 文件
            modelMap = checkoutFromMasterAndReloadModelMap(gitRepoPath, modelMap, hasModel, git, branch);
            long starttime = System.currentTimeMillis();
            if (!isNewBranch && !hasMerge) {
                for (SVNLogEntryPath change : svnLogEntryPaths) {
                    // 从 change.getPath() 中截取 branch 之后的部分
                    String path = change.getPath();

                    String model = null;
                    String realModelName;
                    // 分支名之后的路径
                    String branchPath;
                    if (dirRegx == null || "dev".equals(branch)) {
                        if (path.endsWith(gitRepoName) || !path.contains(gitRepoName)) {
                            continue;
                        }
                        branchPath = path.substring(path.indexOf(gitRepoName) + gitRepoName.length() + 1);
                    } else if ("dev".equals(branch)) {
                        branchPath = path.substring(path.indexOf(gitRepoName) + gitRepoName.length() + 1);
                    } else {
                        branchPath = path.substring(path.indexOf(branch));
                    }
                    if (branchPath.contains(".git")) {
                        continue;
                    }
                    String contentPath = null;
                    Path targetPath = null;
                    String regxStr = null;
                    if (modelMap == null) {
                        // 跳过分支根目录
                        if (branchPath.length() == branch.length()) {
                            logger.info("        暂不跳过1");
                            // continue;
                        }
                        contentPath = dirRegx == null ? branchPath : branchPath.substring(branchPath.indexOf(branch) + branch.length());
                        if (contentPath.startsWith(gitRepoName) || contentPath.startsWith("/" + gitRepoName)) {
                            contentPath = contentPath.substring(contentPath.indexOf(gitRepoName) + gitRepoName.length());
                        } else if (contentPath.startsWith(gitRepoName.toLowerCase()) || contentPath.startsWith("/" + gitRepoName.toLowerCase())) {
                            if (!"Platform".equals(gitRepoName)) {
                                contentPath = contentPath.substring(contentPath.indexOf(gitRepoName.toLowerCase()) + gitRepoName.length());
                            }
                        }
                        targetPath = Paths.get(gitRepoPath, contentPath);
                    } else {
                        model = path.substring(path.indexOf(gitRepoName) + gitRepoName.length() + 1);
                        if (model != null && model.contains("/")) {
                            model = model.substring(0, model.indexOf("/"));
                        }
                        if (modelMap.containsKey(model)) {
                            regxStr = (String) modelMap.get(model).get("str");
                            if (regxStr.startsWith("new:")) {
                                try {
                                    sendMail("Svn2Git", svnRepoPath + " " + version + " 版本出现独立模块");
                                } catch (Exception ignored) {
                                }
                                logger.info("独立模块");
                                continue;
                            } else {
                                if ("dev".equals(branch) && !regxStr.contains("(")) {
                                    branchPath = path.substring(path.indexOf(gitRepoName) + gitRepoName.length() + 1);
                                } else {
                                    branchPath = path.substring(path.indexOf(branch));
                                }
                                realModelName = regxStr.contains("(") ? getRealModelName(model, new File(svnRepoPath + File.separator + model + File.separator + branch)) : model;
                                if (realModelName == null) {
                                    continue;
                                }
                                // 跳过分支根目录
                                if (branchPath.length() == branch.length() + realModelName.length() + 1 || (!regxStr.contains("(") && branchPath.equalsIgnoreCase(realModelName))) {
                                    logger.info("        暂不跳过2");
                                    // continue;
                                }
                                if (regxStr.contains("(")) {
                                    contentPath = branchPath.substring(branchPath.indexOf(branch) + branch.length() + realModelName.length() + 1);
                                } else {
                                    contentPath = branchPath.substring(realModelName.length());
                                }
                                targetPath = Paths.get(gitRepoPath, model, contentPath);
                            }
                        }
                    }

                    File targetFile = targetPath.toFile();
                    if (change.getType() == TYPE_ADDED || change.getType() == TYPE_MODIFIED) {
                        Path sourcePath = model == null || (regxStr != null && !regxStr.contains("(")) ? Paths.get(svnRepoPath, branchPath) : Paths.get(svnRepoPath, model, branchPath);
                        File sourceFile = sourcePath.toFile();
                        if (!sourceFile.exists()) {
                            logger.info("        Source file not exist or source file is directory: " + sourceFile.getAbsolutePath());
                            continue;
                        }
                        Files.createDirectories(targetPath.getParent());
                        if (sourceFile.isDirectory()) {
                            logger.info("        复制目录1: " + sourcePath + " -> " + targetPath);
                        }
                        Files.createDirectories(targetPath.getParent());
                        copyFile(sourceFile, targetFile);
                    } else if (change.getType() == TYPE_DELETED) {
                        if (targetFile.exists()) {
                            if (targetFile.isDirectory()) {
                                // TODO 判断删除分支
                                //      E:\Svn2GitProjects\SvnSyncProjects\SMPlatform
                                //      E:\Svn2GitProjects\GitSyncProjects\Platform
                                logger.info("        删除目录1: " + targetPath);
                            }
                            rmDirs(targetFile);
                        }
                    }
                }
                long costtime = (System.currentTimeMillis() - starttime) / 1000;
                if (costtime > 2L) {
                    logger.info("        " + branch + " 分支修改和删除文件耗时：" + costtime + " 秒");
                }
                starttime = System.currentTimeMillis();
                // 从 master 分支检出 .gitignore 文件
                modelMap = checkoutFromMasterAndReloadModelMap(gitRepoPath, modelMap, hasModel, git, branch);
                int addResult = gitAddAll(gitWorkingDir);
                if (addResult != 0) {
                    logger.error("        " + branch + " 分支 git add . 失败");
                }
                Status status = git.status().call();
                Set<String> uncommittedChanges = status.getUncommittedChanges();
                logger.info("        " + branch + " 分支 git add . 耗时1：" + (System.currentTimeMillis() - starttime) / 1000 + " 秒");
                if (uncommittedChanges.size() > 0) {
                    if ("".equals(commitMsg)) {
                        git.commit().setMessage("SVN version " + version).setCommitter(personIdent).call();
                    } else {
                        git.commit().setMessage("SVN version " + version + ": " + commitMsg).setCommitter(personIdent).call();
                    }
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
                            if (modelMap == null) {
                                logger.info("        删除目录2: " + file.getAbsolutePath());
                                rmDirs(file);
                            } else {
                                String regxStr = null;
                                File svnFile = new File(svnRepoPath + File.separator + fileName);
                                if (modelMap.containsKey(fileName)) {
                                    Map<String, Object> regxMap = modelMap.get(fileName);
                                    regxStr = (String) regxMap.get("str");
                                } else if (modelMap.containsKey(gitRepoName)) {
                                    Map<String, Object> regxMap = modelMap.get(gitRepoName);
                                    regxStr = (String) regxMap.get("str");
                                    svnFile = new File(svnRepoPath);
                                }
                                // 只删除当前分支相关的
                                if (svnFile == null || !svnFile.isDirectory()) {
                                    continue;
                                }
                                List<String> branchs = Arrays.asList(svnFile.list());
                                if (branchs.contains(branch) || (regxStr != null && !regxStr.contains("("))) {
                                    logger.info("        删除目录3: " + file.getAbsolutePath());
                                    rmDirs(file);
                                }
                            }
                        }
                    }
                }
                // 拷贝 svnRepoPath 下所有非 .svn 目录和文件到 gitRepoPath 目录下
                File svnRepo = modelMap == null ? new File(svnRepoPath + File.separator + branch + (suffix == null ? "" : File.separator + suffix)) : new File(svnRepoPath);
                files = svnRepo.listFiles();
                if (files != null) {
                    for (File file : files) {
                        String fileName = file.getName();
                        if (COPY_BLACKLIST.contains(fileName)) {
                            continue;
                        }
                        if (modelMap == null) {
                            String targetPath = gitRepoPath + File.separator + fileName;
                            if (file.isDirectory()) {
                                logger.info("        复制目录2: " + file.getAbsolutePath() + " -> " + targetPath);
                            }
                            copyFile(file, new File(targetPath));
                        } else {
                            String modelName = hasModel ? fileName : modelMap.keySet().stream().findFirst().get();
                            if (modelMap.containsKey(modelName)) {
                                Map<String, Object> regxMap = modelMap.get(modelName);
                                String regxStr = (String) regxMap.get("str");
                                // 独立模块分支也独立，不受影响
                                if (!regxStr.startsWith("new:")) {
                                    String realModelName;
                                    if (hasModel) {
                                        realModelName = regxStr.contains("(") ? getRealModelName(modelName, new File(file.getAbsolutePath() + File.separator + branch)) : fileName;
                                    } else if (regxStr.endsWith(")")) {
                                        if (!fileName.equals(branch)) {
                                            continue;
                                        }
                                        realModelName = modelName;
                                    } else {
                                        realModelName = getRealModelName(modelName, new File(file.getAbsolutePath()));
                                    }
                                    if (realModelName == null) {
                                        continue;
                                    }
                                    if (hasModel) {
                                        file = regxStr.contains("(") ? new File(file.getAbsolutePath() + File.separator + branch + File.separator + realModelName) : file;
                                    } else {
                                        file = regxStr.endsWith(")") ? file : new File(file.getAbsolutePath() + File.separator + realModelName);
                                    }
                                    if (!file.exists()) {
                                        continue;
                                    }
                                    String targetPath = hasModel ? gitRepoPath + File.separator + modelName : gitRepoPath;
                                    if (file.isDirectory()) {
                                        logger.info("        复制目录3: " + file.getAbsolutePath() + " -> " + targetPath);
                                    }
                                    copyFile(file, new File(targetPath));
                                }
                            } else if (file.isDirectory()) {
                                // 未知模块
                                if (!MODEL_BLACKLIST.contains(modelName)) {
                                    try {
                                        sendMail("Svn2Git", "未知模块: " + modelName + "\n及时确认是否需要添加映射");
                                    } catch (Exception ignored) {
                                    }
                                    logger.info("        未知模块: " + modelName);
                                }
                            } else if (hasModel) {
                                logger.info("        复制文件1: " + file.getAbsolutePath() + " -> " + gitRepoPath + File.separator + modelName);
                                copyFile(file, new File(gitRepoPath + File.separator + modelName));
                            } else {
                                String realModelName = getRealModelName(modelName, new File(file.getAbsolutePath()));
                                file = new File(file.getAbsolutePath() + File.separator + realModelName);
                                logger.info("        复制文件2: " + file.getAbsolutePath() + " -> " + gitRepoPath);
                            }
                        }
                    }
                }
                long costtime = (System.currentTimeMillis() - starttime) / 1000;
                if (costtime > 2L) {
                    logger.info("        " + branch + " 分支修改和删除文件耗时：" + costtime + " 秒");
                }
                // 从 master 分支检出 .gitignore 文件
                modelMap = checkoutFromMasterAndReloadModelMap(gitRepoPath, modelMap, hasModel, git, branch);
                starttime = System.currentTimeMillis();
                int addResult = gitAddAll(gitWorkingDir);
                if (addResult != 0) {
                    logger.error("        " + branch + " 分支 git add . 失败");
                }
                Status status = git.status().call();
                Set<String> uncommittedChanges = status.getUncommittedChanges();
                logger.info("        " + branch + " 分支 git add . 耗时2：" + (System.currentTimeMillis() - starttime) / 1000 + " 秒");
                if (uncommittedChanges.size() > 0) {
                    if ("".equals(commitMsg)) {
                        git.commit().setMessage("SVN version " + version).setCommitter(personIdent).call();
                    } else {
                        git.commit().setMessage("SVN version " + version + ": " + commitMsg).setCommitter(personIdent).call();
                    }
                }
                lastFixVersion.put(branch, version);
                writeFixVersion(gitRepoPath + File.separator + FORCE_FIX_VERSION_FILE, lastFixVersion);
            }
        }
        try {
            git.push().setCredentialsProvider(credentialsProvider).setPushAll().call();
        } catch (Exception ignore) {
            try {
                logger.info("  push 失败，尝试强制 push");
                git.push().setCredentialsProvider(credentialsProvider).setPushAll().setForce(true).call();
            } catch (Exception e) {
                e.printStackTrace();
                try {
                    sendMail("Svn2Git", "git push 异常: " + e.getMessage());
                } catch (Exception ignored) {
                }
                logger.info("        git push 异常: " + e.getMessage());
                System.exit(1);
            }
        }
        git.close();
        if (highestVersion > version) {
            version = highestVersion;
        }
        if (version > 0L) {
            Files.write(Paths.get(gitRepoPath, ".svn_version"), String.valueOf(version).getBytes(), StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
        }
        return version;
    }

    private static void checkMergeAction(String svnRepoPath, long version, String branch, Set<String> mergeSet, String path, String copyPath) {
        if (copyPath != null) {
            String fromBranchRegStr = path.replace(branch, "(.*)");
            Pattern fromBranchPattern = Pattern.compile(fromBranchRegStr);
            Matcher matcher = fromBranchPattern.matcher(copyPath);
            if (matcher.find()) {
                String fromBranch = matcher.group(1);
                fromBranch = fromBranch.contains("/") ? fromBranch.substring(0, fromBranch.indexOf("/")) : fromBranch;
                String fromto = fromBranch + "->" + branch;
                if (!branch.equals(fromBranch) && !mergeSet.contains(fromto)) {
                    mergeSet.add(fromto);
                }
            }
        }
    }

    private Map<String, Map<String, Object>> checkoutFromMasterAndReloadModelMap(String gitRepoPath, Map<String, Map<String, Object>> modelMap, boolean hasModel, Git git, String branch) throws GitAPIException {
        if (!"master".equals(branch)) {
            git.checkout().addPath(".gitignore").setForced(true).setStartPoint("master").call();
            git.checkout().addPath("svn_git_map.properties").setForced(true).setStartPoint("master").call();
            if (modelMap != null && hasModel) {
                modelMap = readModelMap(gitRepoPath + File.separator + MODEL_MAP_FILE);
            }
            git.checkout().addPath("README.md").setForced(true).setStartPoint("master").call();
            git.checkout().addPath("hooks").setForced(true).setStartPoint("master").call();
            git.checkout().addPath("config.bat").setForced(true).setStartPoint("master").call();
            git.checkout().addPath("config.sh").setForced(true).setStartPoint("master").call();
        }
        return modelMap;
    }

    /**
     * 检出或创建新分支
     *
     * @param branch 目标分支
     * @return 是否创建新分支
     */
    private boolean checkoutOrCreateBranch(Git git, CredentialsProvider credentialsProvider, String branch) throws GitAPIException, IOException {
        String currentBranch = git.getRepository().getBranch();
        logger.info("    当前分支：" + currentBranch + ", 目标分支：" + branch);
        if (currentBranch.equals(branch)) {
            FetchResult fetchResult = git.fetch().setCredentialsProvider(credentialsProvider).call();
            PullResult pullResult = git.pull().setCredentialsProvider(credentialsProvider).call();
            return false;
        }
        try {
            git.checkout().setName(branch).call();
            FetchResult fetchResult = git.fetch().setCredentialsProvider(credentialsProvider).call();
            PullResult pullResult = git.pull().setCredentialsProvider(credentialsProvider).call();
            return false;
        } catch (RefNotFoundException e) {
            try {
                sendMail("Svn2Git", git.getRepository().toString() + " 将要创建新分支: " + branch);
            } catch (Exception ignored) {
            }
            try {
                // 尝试检出远程分支
                git.checkout().setCreateBranch(true).setName(branch).setUpstreamMode(CreateBranchCommand.SetupUpstreamMode.TRACK).setStartPoint("origin/" + branch).call();
            } catch (RefNotFoundException rnfe) {
                logger.info("    远程分支未找到，直接创建新分支：" + branch);
                git.checkout().setCreateBranch(true).setName(branch).call();
            }
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

    private Map<String, Map<String, Object>> readModelMap(String filePath) {
        try (Scanner scanner = new Scanner(new File(filePath))) {
            Map<String, Map<String, Object>> modelMap = new HashMap<>();
            while (scanner.hasNextLine()) {
                Map<String, Object> map = new HashMap<>(2);
                String line = scanner.nextLine();
                if (line.isEmpty()) {
                    continue;
                }
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
        } catch (FileNotFoundException ignored) {
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

    public void sendMail(String title, String content) throws Exception {
        sendMail(title, content, null);
    }

    public void sendMail(String title, String content, String to) throws Exception {

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
        if (to == null) {
            to = recipient;
        }
        message.setRecipients(Message.RecipientType.TO, InternetAddress.parse(to));
        message.setSubject(title);

        message.setContent(content, "text/html;charset=UTF-8");

        Transport.send(message);
    }

    private Map<String, Long> readFixVersion(String filePath) {
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
            logger.info("File not found: " + filePath);
        } catch (NumberFormatException e) {
            // handle number format error
            logger.info("Invalid version number");
        }

        return lastFixVersion;
    }

    private void writeFixVersion(String filePath, Map<String, Long> lastFixVersion) {
        try (FileWriter fileWriter = new FileWriter(filePath); BufferedWriter writer = new BufferedWriter(fileWriter)) {
            for (Map.Entry<String, Long> entry : lastFixVersion.entrySet()) {
                writer.write(entry.getKey() + "=" + entry.getValue());
                writer.newLine();
            }
        } catch (IOException e) {
            // handle IO error
            logger.info("Error writing to file");
        }
    }
}
