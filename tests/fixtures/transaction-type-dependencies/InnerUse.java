package fixture;
import org.springframework.stereotype.Service;
@Service class Entry {
    class Helper { void work() {} }
    Helper helper;
    public void run() { helper.work(); }
}
